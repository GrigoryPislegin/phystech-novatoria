try {
  const indexes = db.candidates.getIndexes();

  const textIndexes = indexes.filter((idx) =>
    Object.values(idx.key || {}).some((v) => v === "text")
  );

  if (textIndexes.length > 0) {
    for (const idx of textIndexes) {
      try {
        db.candidates.dropIndex(idx.name);
        print(`[migration] Dropped text index: ${idx.name}`);
      } catch (e) {
        print(`[migration] Failed to drop index ${idx.name}: ${e.message}`);
      }
    }
  } else {
    pass
  }
  db.candidates.createIndex(
    {
      resume: "text",
      name: "text",
      city: "text",
      country: "text",
      notes: "text",
      email: "text",
      phone_number: "text",
    },
    {
      name: "candidate_text",
      default_language: "russian",
      language_override: "language",
    }
  );
  db.candidates.getIndexes().forEach((i) => printjson(i));
} catch (error) {
  print("[migration] Error: " + error.message);
}


