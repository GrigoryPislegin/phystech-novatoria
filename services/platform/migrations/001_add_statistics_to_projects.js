const projects = db.projects.find({}).toArray();

for (const project of projects) {
  const stats = {
    total_candidates: db.candidates.countDocuments({
      "project.$id": project._id,
      deleted_at: null,
    }),
    total_vacancies: db.vacancies.countDocuments({
      "project.$id": project._id,
      deleted_at: null,
    }),
    active_vacancies: db.vacancies.countDocuments({
      "project.$id": project._id,
      deleted_at: null,
      status: "open",
    }),
  };

  db.projects.updateOne({ _id: project._id }, { $set: { statistics: stats } });
}

const vacancies = db.vacancies.find({}).toArray();

for (const vacancy of vacancies) {
  const stats = {
    total_candidates: db.candidates.countDocuments({
      "vacancy.$id": vacancy._id,
      deleted_at: null,
    }),
    platform_candidates: db.candidates.countDocuments({
      "vacancy.$id": vacancy._id,
      deleted_at: null,
      source: "nanimai",
    }),
    delegated_candidates: db.candidates.countDocuments({
      "vacancy.$id": vacancy._id,
      deleted_at: null,
      source: { $ne: "nanimai" },
    }),
  };

  db.vacancies.updateOne({ _id: vacancy._id }, { $set: { statistics: stats } });
}
