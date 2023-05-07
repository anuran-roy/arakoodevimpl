import os

import numpy as np
import openai
import pinecone
from dotenv import load_dotenv

load_dotenv()

query = "how long does it take to remove wisdom tooth"
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.organization = "org-bWPRxgvD4e3jFTVqMKVBiGMp"

pinecone.init(api_key=os.getenv("PINECONE_API_KEY"), environment="northamerica-northeast1-gcp")
index = pinecone.Index("hyde")


result = openai.Completion.create(
    engine="text-davinci-003",
    prompt=query,
    temperature=0.7,
    n=8,
    max_tokens=512,
    top_p=1,
    stop=['\n\n\n'],
    logprobs=1
)
#
# samples = [
#     "However, if you do feel pain during the procedure, tell your dentist or oral surgeon so they can give you more anaesthetic. How long it takes to remove the tooth will vary. Simple procedures can take a few ""minutes, but it can take longer than 20 minutes if it's more complicated.",
#     "Your surgery should take 45 minutes or less. You'll get one of these types of anesthesia so you don't feel pain during the removal: Local: Your doctor will numb your mouth with a shot of local anesthetic such as novocaine, lidocaine or mepivicaine.",
#     "The time it takes to remove the tooth will vary. Some procedures only take a few minutes, whereas others can take 20 minutes or longer. After your wisdom teeth have been removed, you may experience swelling and discomfort, both on the inside and outside of your mouth. This is usually worse for the first three days, but it can last for up to two weeks. Read more about how a wisdom tooth is removed and recovering from wisdom tooth removal.",
#     "How long does it take to remove all wisdom teeth?   I got my wisdom teeth removed 5 days ago. I received intravenous anesthesia, so I was not conscious during the process, but those present said it only took about 35 to 40â€¦ minutes for removal."
#     "Complications like infection can lengthen the time it takes to heal up, but here is a general timeline: 1  Swelling and pain will be the greatest during the first 3 days (peaking at about 48hours). 2  Normally, the sockets should take about 2 weeks to 1 month to cover over with solid gum tissue after scabbing first.",
#     "How wisdom teeth are removed. Your dentist may remove your wisdom teeth or they may refer you to a specialist surgeon for hospital treatment. Before the procedure, you'll usually be given a local anaesthetic injection to numb the area around the tooth.he time it takes to remove the tooth will vary. Some procedures only take a few minutes, whereas others can take 20 minutes or longer. After your wisdom teeth have been removed, you may experience swelling and discomfort, both on the inside and outside of your mouth."
# ]

#
#
# Inserted once and hence commented out
#
#
# sample_vectors = []
# for idx, sample in enumerate(samples):
#     embedding = openai.Embedding.create(
#         input=sample.strip(), model="text-embedding-ada-002"
#     )["data"][0]["embedding"]
#     sample_vectors.append((str(idx), embedding, {"content": sample}))
# upsert_response = index.upsert(
#     sample_vectors,
# )

# logarithmic probability sorting
to_return = []
for _, val in enumerate(result['choices']):
    text = val['text']
    logprob = sum(val['logprobs']['token_logprobs'])
    to_return.append((text, logprob))
texts = [r[0] for r in sorted(to_return, key=lambda tup: tup[1], reverse=True)]

print(">Generated responses:")
text_embeddings = []
for idx, doc in enumerate(texts):
    print(doc.strip())
    embedding = openai.Embedding.create(
        input=doc.strip(), model="text-embedding-ada-002"
    )["data"][0]["embedding"]
    text_embeddings.append(embedding)
# merging response embeddings
text_embeddings = np.array(text_embeddings)
mean_embedding = np.mean(text_embeddings, axis=0)
result_vector = mean_embedding.reshape((1, len(mean_embedding)))
# retrieving k most similar documents
query_response = index.query(top_k=2, include_metadata=True, vector=result_vector[0].tolist())
print(">Retrieved documents")
for res in query_response.matches:
    print(res['metadata']['content'])
