#!/bin/bash
# Helper script to update the kisune dev-workflow skills in the project
cp -r ~/kisune/dev-workflow/skills/* .agents/skills/
git add .agents/skills/
git commit -m "chore: update kisune dev-workflow skills"
