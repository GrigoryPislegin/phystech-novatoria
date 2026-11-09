use nanimai_platform;

db.vacancies.updateMany({}, {
  $set: {
    stages: [
      { stage: "rejected_user", shown: true },
      { stage: "rejected", shown: true },
      { stage: "magic-ai", shown: true },
      { stage: "new", shown: true },
      { stage: "selected", shown: true },
      { stage: "message", shown: true },
      { stage: "preliminary_call", shown: true },
      { stage: "interview", shown: true },
      { stage: "test_task", shown: true },
      { stage: "final_test", shown: true },
      { stage: "offer", shown: true },
      { stage: "accepted", shown: true },
    ]
  }
});
