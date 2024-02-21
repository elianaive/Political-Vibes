import pandas as pd
from angle_emb import AnglE
import torch
import h5py
import numpy as np

# Load the CSV file into a DataFrame
data = pd.read_csv('data/bills_117_summarized_test.csv')

# Initialize the AnglE model
angle = AnglE.from_pretrained('WhereIsAI/UAE-Large-V1', pooling_strategy='cls').cuda()

# Function to encode summaries using AnglE
def encode_summaries(summaries, batch_size=100):
    # Prepare an empty list to hold all batched embeddings
    all_embeddings = []
    
    for i in range(0, len(summaries), batch_size):
        batch = [summary for summary in summaries[i:i + batch_size] if not pd.isna(summary)]
        # Encode the current batch
        batch_embeddings = angle.encode(batch, to_numpy=True)
        all_embeddings.append(batch_embeddings)
    
    # Concatenate all batch embeddings into a single array
    encoded_vectors = np.concatenate(all_embeddings, axis=0)
    
    return encoded_vectors

# Extract llm_summary column and bill numbers from the DataFrame
summaries = data['llm_summary'].tolist()

bill_info = data['bill'].tolist()  # Assuming the column is named 'bill_number'

# Encode the summaries
encoded_vectors = encode_summaries(summaries)

print(encoded_vectors[0])
print(len(encoded_vectors[0]))

# Save the encoded vectors and bill numbers to an HDF5 file
with h5py.File('data/encoded_vectors.h5', 'w') as hf:
    hf.create_dataset('vectors', data=encoded_vectors)
    hf.create_dataset('bill_info', data=np.array(bill_info, dtype='S'))  # Saving as bytes
