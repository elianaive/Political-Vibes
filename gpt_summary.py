import os
import pandas as pd
import asyncio
import openai
from dotenv import load_dotenv
from tqdm.asyncio import tqdm  # Import the asyncio version of tqdm

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

model = "gpt-3.5-turbo-0125"
context_window = 16000

async def process_row(client, row, prompt_instructions):
    prompt = [
        {
            "role": "system",
            "content": prompt_instructions
        },
        {
            "role": "user",
            "content": row['text']
        }
    ]
    try:
        completion = await client.chat.completions.create(
            model="gpt-3.5-turbo-0125",  # Ensure the model identifier is correct
            messages=prompt
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error processing row: {e}")
        return None

def is_text_too_large(text, max_tokens=context_window):
    token_estimate = len(text) / 4
    return token_estimate > max_tokens

async def main():
    df = pd.read_csv('data/bills_117_test.csv')

    with open('prompt.txt', 'r') as file:
        prompt_instructions = file.read()

    client = openai.AsyncClient(api_key=api_key)

    # Wrap tasks in tqdm for asynchronous progress tracking
    tasks = [process_row(client, row, prompt_instructions) for index, row in df.iterrows() if not is_text_too_large(row['text'])]
    results = await tqdm.gather(*tasks, desc="Processing rows")

    for i, result in enumerate(results):
        if result is not None:
            df.at[i, 'llm_summary'] = result

    df.to_csv('data/bills_117_summarized_test.csv', index=False)

    print("CSV file with LLM summaries has been created.")

if __name__ == "__main__":
    asyncio.run(main())
