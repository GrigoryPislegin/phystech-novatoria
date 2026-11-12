use nanimai_platform;

db.statistics.find(
    { "date_increase_statistics.statistics": { $exists: true } }
).forEach(all_stats => {
    const date_stats = all_stats.date_increase_statistics?.statistics;
    if (!date_stats) return;

    let changed = false;

    for (const day in date_stats) {
        if (!date_stats[day] || typeof date_stats[day] !== "object") continue;

        if (date_stats[day].platform !== undefined) {
            date_stats[day].nanimai = date_stats[day].platform;
            delete date_stats[day].platform;
            changed = true;
            }
        }

    if (changed) {
        db.statistics.updateOne(
        { _id: all_stats._id },
        { $set: { "date_increase_statistics.statistics": date_stats } }
        );
    }
});
