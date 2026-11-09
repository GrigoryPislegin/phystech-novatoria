use nanimai_platform;

db.projects.updateMany(
  { template_settings: { $exists: false } },
  {
    $set: {
      template_settings: {
        logo_url: null,
        logo_format: null,
        main_color: null,
        without_nanimai_attributes: false
      }
    }
  }
);
