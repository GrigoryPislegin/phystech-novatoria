use nanimai_platform;

db.user_profiles.updateMany(
  {}, { $unset: { hharon_id: 1 } },
);
