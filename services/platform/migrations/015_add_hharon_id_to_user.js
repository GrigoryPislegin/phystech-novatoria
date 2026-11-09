use nanimai_platform;

db.user_profiles.updateMany(
  { hharon_id: { $exists: false } },
  { $set: { hharon_id: null } }
);
