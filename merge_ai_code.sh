#!/bin/bash

# Variables
FEATURE_BRANCH="ai_generated"
MASTER_BRANCH="master"
REMOTE="origin"

# Stage all changes (new files, modifications, and deletions)
git add -A
git commit -m "Autocommit: stage all changes before merge" || echo "No changes to commit."

# Fetch latest changes from the remote
git fetch $REMOTE

# Checkout master and pull the latest changes
git checkout $MASTER_BRANCH
git pull $REMOTE $MASTER_BRANCH

# Checkout feature branch and merge master into it
git checkout $FEATURE_BRANCH
git merge $MASTER_BRANCH

# Switch back to master and merge the feature branch into it
git checkout $MASTER_BRANCH
git merge $FEATURE_BRANCH

# Push master to remote
git push $REMOTE $MASTER_BRANCH

# Switch back to the feature branch to continue work
git checkout $FEATURE_BRANCH

echo "Merged $FEATURE_BRANCH into $MASTER_BRANCH successfully and returned to $FEATURE_BRANCH."
