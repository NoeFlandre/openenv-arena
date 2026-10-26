# QE Arena v7 redraw (NoeFlandre)

This folder republishes the **QE Arena terminal** OpenEnv environment by Profa-QE
(Dragan Spiridonov, MIT License, https://github.com/proffesor-for-testing/openenv-qe-arena)
under `ghcr.io/noeflandre/workbench-gym:v8-qe`, for one OpenEnv Arena submission.

The image is a label-only overlay of
`ghcr.io/proffesor-for-testing/openenv-qe-arena-terminal@sha256:9307e4e603d45b4b9800dcb820811516ea64313562fbb2082fb0f147c5eed85b`:
same server, tasks, graders and start command. The submission repeats Profa-QE's public
v7 request (`submission/request-v7r5.json` upstream): seven terminal tasks
(`qe_skill-science-d2`, `-science-d3`, `-math-d1`, `-math-d2`, `-math-d3`, `-media-d1`,
`-media-d2`) with the same schema, limits, example and finish actions.

Why: on the arena board Profa-QE reported that five unchanged draws of that request
solved a held-out media task four times, against about 2% of other runs. Media is a domain
where this account has no solve yet.

All credit for the environment goes to Profa-QE. Its MIT license is in
`LICENSE-openenv-qe-arena`.
