const vacanciesCollection = db.collection('vacancies');

const cursor = vacanciesCollection.find({
  'stages': {
    $not: {
      $elemMatch: {
        'stage': 'magic-ai'
      }
    }
  }
});

cursor.forEach(async (vacancy) => {
  const stages = vacancy.stages || [];
  stages.unshift({ stage: 'magic-ai', shown: true });

  vacanciesCollection.updateOne(
    { _id: vacancy._id },
    { $set: { stages: stages } }
  );
});
