const candidates = db.candidates
  .find({ first_name: { $exists: true } })
  .toArray();

const changes = [];

for (const candidate of candidates) {
  const first_name = candidate.first_name || "";
  const last_name = candidate.last_name || "";
  const full_name = (first_name + " " + last_name).trim();

  changes.push({
    updateOne: {
      filter: { _id: candidate._id },
      update: {
        $set: { name: full_name },
        $unset: { first_name: "", last_name: "" },
      },
    },
  });
}

if (changes.length > 0) {
  collection.bulkWrite(changes);
}

print("migration complete");
