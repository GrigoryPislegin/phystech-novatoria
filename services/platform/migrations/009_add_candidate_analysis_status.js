use nanimai_platform;

db.candidates.updateOne({"analysis_status": { $exists: false }}, { $set: { "analysis_status": "success" } })


