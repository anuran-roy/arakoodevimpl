import gensim.models as g

model = g.Doc2Vec.load("model/new.model")
res = model.infer_vector("In the above instantiation, we have defined the vector of size 40 with a minimum count of 2 words with 30 epochs. Now we can convert the format of words using the following lines of codes:".split(" "))

print(len(res))
