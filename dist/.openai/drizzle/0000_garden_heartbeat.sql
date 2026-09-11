CREATE TABLE IF NOT EXISTS garden_heartbeat (
  id INTEGER PRIMARY KEY CHECK(id=1),
  observed REAL NOT NULL,
  body TEXT NOT NULL
);
