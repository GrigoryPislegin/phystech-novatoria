use nanimai_plaform;

db.candidates.updateMany(
  { criteria: null },
  { $set: { criteria: {} } }
);

db.candidates.updateMany(
  { stop_factors: null },
  { $set: { stop_factors: {} } }
);
