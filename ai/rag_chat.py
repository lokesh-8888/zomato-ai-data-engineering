import os
import numpy as np
import pandas as pd
import snowflake.connector
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

EMBEDDING_MODEL = "openai/text-embedding-3-small"
CHAT_MODEL = "openai/gpt-4o-mini"
NEW_REVIEWS = 500
TOK_K = 5
CACHE_FILE = os.path.join(os.path.dirname(__file__), "review_embeddings.parquet")

openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
if not openrouter_api_key:
    raise RuntimeError(
        "OPENROUTER_API_KEY is not set. Add it to ai/.env before running this app."
    )

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=openrouter_api_key,
)
def read_reviews_from_snowflake():
    conn = snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
    )

    query = f"""
        SELECT REVIEW_ID, CITY, RATING, COMMENT
        FROM ZOMATO.STAGING.STG_REVIEWS
        SAMPLE ({NEW_REVIEWS} ROWS)
    """
    df = conn.cursor().execute(query).fetch_pandas_all()
    conn.close()

    df.columns = [col.lower() for col in df.columns]
    return df

def embed(texts):
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts)

    return [item.embedding for item in response.data]
    
def load_reviews():
    if os.path.exists(CACHE_FILE):
        return pd.read_parquet(CACHE_FILE)

    df = read_reviews_from_snowflake()
    df['embedding'] = embed(df['comment'].tolist())
    df.to_parquet(CACHE_FILE)
    return df

def cosine_similarity(vec_a, vec_b):
    return np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

def find_similar_reviews(question, df):
    question_vector = embed([question])[0]

    scores = []
    for review_vector in df['embedding']:
        scores.append(cosine_similarity(question_vector, review_vector))

    df = df.copy()
    df['score'] = scores
    return df.nlargest(TOK_K, 'score')

def ask_llm(question, top_reviews):
    context = ""

    for _, row in top_reviews.iterrows():
        context += f" ({row['city']}, {row['rating']} stars) {row['comment']}\n"

    system_prompt = (
        "Answer ONLY using the customer reviews provided. "
        "Be concise. If the reviews don't cover it, say so."
    )

    user_prompt = f"Question: {question}\n\nReviews:\n{context}"

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content
    
@st.cache_data(show_spinner="Loading reviews and embeddings...")
def load_reviews_for_app():
    return load_reviews()


def main():
    st.set_page_config(page_title="Zomato Review Assistant", page_icon="🍽️")
    st.title("Zomato Review Assistant")
    st.caption("Ask questions about customer reviews.")

    try:
        review_df = load_reviews_for_app()
    except Exception as error:
        st.error(f"Could not load reviews: {error}")
        st.stop()

    question = st.chat_input("What are customers saying about delivery?")
    if not question:
        return

    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching reviews..."):
            try:
                top_reviews = find_similar_reviews(question, review_df)
                answer = ask_llm(question, top_reviews)
            except Exception as error:
                st.error(f"Could not answer the question: {error}")
                return

        st.write(answer)
        with st.expander("Reviews used"):
            for _, row in top_reviews.iterrows():
                st.write(f"**{row['city']}**, {row['rating']} stars: {row['comment']}")


if __name__ == "__main__":
    main()
