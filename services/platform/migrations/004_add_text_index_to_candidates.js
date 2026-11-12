// Create text index on resume field for efficient text search
try {
  db.candidates.createIndex(
    { resume: "text" },
    {
      name: "resume_text_index",
      default_language: "russian",
      language_override: "language"
    }
  );
  print("Text index on resume field created successfully");
} catch (error) {
  print("Error creating text index: " + error.message);
}
