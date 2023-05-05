import os

import numpy as np
import openai
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()
openai.organization = os.getenv("ORG")
openai.api_key = os.getenv("API_KEY")

# Get gpt response on prompt and generate a vector embedding
messages = [{"role": "user", "content": "how long does it take to remove wisdom tooth"}]
completion = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, temperature=0.9, n=5)
responses = []
response_embeddings = []
for val in completion.choices:
    res = val.message.content
    responses.append(res)
    response_embeddings.append(np.array(openai.Embedding.create(input=res, engine="text-embedding-ada-002")["data"]
                                        [0]["embedding"]))

# sample documents rather than a database
samples = [
    "However, if you do feel pain during the procedure, tell your dentist or oral surgeon so they can give you more anaesthetic. How long it takes to remove the tooth will vary. Simple procedures can take a few ""minutes, but it can take longer than 20 minutes if it's more complicated.",
    "Your surgery should take 45 minutes or less. You'll get one of these types of anesthesia so you don't feel pain during the removal: Local: Your doctor will numb your mouth with a shot of local anesthetic such as novocaine, lidocaine or mepivicaine.",
    "The time it takes to remove the tooth will vary. Some procedures only take a few minutes, whereas others can take 20 minutes or longer. After your wisdom teeth have been removed, you may experience swelling and discomfort, both on the inside and outside of your mouth. This is usually worse for the first three days, but it can last for up to two weeks. Read more about how a wisdom tooth is removed and recovering from wisdom tooth removal.",
    "How long does it take to remove all wisdom teeth?   I got my wisdom teeth removed 5 days ago. I received intravenous anesthesia, so I was not conscious during the process, but those present said it only took about 35 to 40â€¦ minutes for removal."
    "Complications like infection can lengthen the time it takes to heal up, but here is a general timeline: 1  Swelling and pain will be the greatest during the first 3 days (peaking at about 48hours). 2  Normally, the sockets should take about 2 weeks to 1 month to cover over with solid gum tissue after scabbing first.",
    "How wisdom teeth are removed. Your dentist may remove your wisdom teeth or they may refer you to a specialist surgeon for hospital treatment. Before the procedure, you'll usually be given a local anaesthetic injection to numb the area around the tooth.he time it takes to remove the tooth will vary. Some procedures only take a few minutes, whereas others can take 20 minutes or longer. After your wisdom teeth have been removed, you may experience swelling and discomfort, both on the inside and outside of your mouth."
]

# get document embeddings
sample_embeddings = []
for sample in samples:
    sample_embeddings.append(np.array(openai.Embedding.create(input=sample, engine="text-embedding-ada-002")["data"]
                                      [0]["embedding"]))

# compare embeddings and choose the document with the highest similarity
for idx, re in enumerate(response_embeddings):
    cosine_similarities = []
    print(f"{responses[idx]}:")
    for se in sample_embeddings:
        cosine_similarities.append(cosine_similarity(re.reshape(1, -1), se.reshape(1, -1)))
    print(cosine_similarities)
    print(samples[cosine_similarities.index(max(cosine_similarities))])
    print()

# Another interesting mapping is to eliminate already chosen document from the list
for idx, re in enumerate(response_embeddings):
    cosine_similarities = []
    print(f">Prompt:\n{responses[idx]}:")
    for se in sample_embeddings:
        cosine_similarities.append(cosine_similarity(re.reshape(1, -1), se.reshape(1, -1)))
    max_sample_idx = cosine_similarities.index(max(cosine_similarities))
    print(f">Document:\n{samples[max_sample_idx]}")
    del samples[max_sample_idx]
    del sample_embeddings[max_sample_idx]
    print()
