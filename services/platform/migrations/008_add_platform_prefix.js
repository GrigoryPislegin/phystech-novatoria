use nanimai_plaform;

var config = {
  _id: "rs0",
  members: [
    { _id: 0, host: "platform_mongodb_master:27017", priority: 2 },
    { _id: 1, host: "platform_mongodb_slave_1:27017", priority: 1 },
  ],
}

rs.reload(config, { force: true })
