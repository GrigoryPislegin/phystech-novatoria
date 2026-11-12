use nanimai_platform;

db.candidates.updateMany(
  { contacts: { $exists: false } },
  {
    $set: {
      contacts: {}
    }
  }
);
