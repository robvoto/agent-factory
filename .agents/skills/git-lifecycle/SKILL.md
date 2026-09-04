---
name: git-lifecycle
description: Use for branch/worktree setup, commit, push, pull request, merge/integration, main-branch verification, or whenever Git state is unclear.
---

# Skill: Git Lifecycle

Use this whenever code work is started or finished, or whenever the user asks about commit/push/PR/merge/main/deploy state.

## Operator contract

The human should not need to remember Git mechanics.

- Implementation work may be committed to the task branch and that branch may be pushed after validation unless the human explicitly says not to push.
- A pushed task branch is **not** the same as integration to `main`.
- `commit` or `push` alone never means "merge to main".
- `approved`, `merge it`, `put it in main`, `ship it`, or equivalent approval referring to the current completed task authorizes integration to `main`.
- If integration intent is unclear, ask one concise question before merging: `Work is ready on <branch> but is NOT in main. Merge to main now?`
- A pull request is optional unless the repository explicitly requires one or the human explicitly asks for one. Do not create a PR merely because a branch was pushed.

## Before editing

1. Fetch `origin`.
2. Inspect `git status`, current branch/worktree, `HEAD`, and `origin/main`.
3. Preserve unrelated dirty work. Never stash, reset, overwrite, or commit another agent's changes without explicit coordination.
4. When concurrent work is possible, use an isolated task branch + worktree based on current `origin/main`; do not code in the shared `main` checkout.

## Before integration

1. Confirm the exact task commit SHA and that validation passed.
2. Fetch `origin` again and compare the task branch with current `origin/main`.
3. If `origin/main` advanced since the task branch was cut, do not blindly push, force-push, or pretend it is a fast-forward.
4. Build the integration result from the **current** `origin/main` plus the task branch, using the repository's documented merge strategy. If none is documented, prefer a normal non-force merge that preserves both histories.
5. If there are conflicts, unrelated-history surprises, unclear ownership, failed tests, or ambiguity about how to reconcile changes, stop and ask the human instead of improvising.
6. Re-run the required validation on the integrated result before updating `main`.
7. Push `main` without force. If the remote moved again and rejects the push, fetch and reassess; never bypass the rejection with force.

## Required verification

After any claimed integration, prove it instead of inferring it:

- Fetch `origin`.
- Verify the task commit is an ancestor of `origin/main` (for example with `git merge-base --is-ancestor <task-sha> origin/main`).
- Record the resulting `origin/main` SHA.
- Do not claim deployment merely because `main` was pushed; verify the repository's actual deployment mechanism separately when deployment matters.

## Mandatory status wording

Never leave the human guessing. End Git-related work with exactly one clear integration state:

- `MAIN STATUS: NOT IN MAIN — uncommitted work`;
- `MAIN STATUS: NOT IN MAIN — committed on <branch>`;
- `MAIN STATUS: NOT IN MAIN — pushed branch <branch>`; or
- `MAIN STATUS: IN MAIN — verified on origin/main at <sha>`.

If the state is not `IN MAIN`, say what single action is still required. Do not use `done`, `shipped`, `merged`, or `deployed` ambiguously.

## Cleanup

After successful integration, remove the task worktree and task branch when it is safe and no longer needed. Never delete a branch/worktree that contains unmerged or unverified work.
