# data/

Only one file belongs here now: your trained `gradient_boosting_model.pkl`
(pointed at by `CLASSIFICATION_MODEL_PATH` in `.env`).

**No dataset CSV goes here anymore.** In this refined architecture, Agent 1 and
Agent 2 both query Space-Track.org live for every request instead of reading a
locally collected dataset. See `SPACETRACK_USERNAME`/`SPACETRACK_PASSWORD` in
`.env.example`.
