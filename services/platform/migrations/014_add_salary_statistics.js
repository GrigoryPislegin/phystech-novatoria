use nanimai_platform;

db.statistics.updateMany(
  { salary_statistics: { $exists: false } },
  { $set: { salary_statistics: { currency: "RUB", count: 0, average: 0.0, median: 0.0 } } }
);
