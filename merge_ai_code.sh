#!/bin/bash

# Variables
FEATURE_BRANCH="ai_generated"
MASTER_BRANCH="master"
REMOTE="origin"

# Fetch latest changes
git fetch $REMOTE

# Checkout master and pull latest
git checkout $MASTER_BRANCH
git pull $REMOTE $MASTER_BRANCH

# Checkout feature branch and merge master into it
git checkout $FEATURE_BRANCH
git merge $MASTER_BRANCH

# Resolve conflicts if any
# (Manual intervention required if conflicts arise)

# Switch back to master and merge feature branch
git checkout $MASTER_BRANCH
git merge $FEATURE_BRANCH

# Push master to remote
git push $REMOTE $MASTER_BRANCH

echo "Merged $FEATURE_BRANCH into $MASTER_BRANCH successfully."

