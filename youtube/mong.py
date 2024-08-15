from pymongo import MongoClient

client = MongoClient("mongodb://127.0.0.1:27017/")

db = client.youtube
coll = db.videos

test_data = {"my_vid": 123}

coll.insert_one(test_data)

z = coll.find_one()

# coll.delete_one(z)

print(z)


