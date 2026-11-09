const candidates = db.candidates
  .find({ criteria: { $exists: false } })
  .toArray();

const changes = [];

for (const candidate of candidates) {
  changes.push({
    updateOne: {
      filter: { _id: candidate._id },
      update: { $set: { criteria: null } },
    },
  });
}

if (changes.length > 0) {
  db.candidates.bulkWrite(changes);
}
