const vacancies = db.vacancies
  .find({ threshold: { $exists: false } })
  .toArray();

const changes = [];

for (const vacancy of vacancies) {
  changes.push({
    updateOne: {
      filter: { _id: vacancy._id },
      update: { $set: { threshold: 0.8 } },
    },
  });
}

if (changes.length > 0) {
  db.vacancies.bulkWrite(changes);
}
