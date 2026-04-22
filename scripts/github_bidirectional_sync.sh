#!/usr/bin/env bash
# GitHub 双向同步：fetch →（可选提交）→ pull → push
# - 已链接 origin（如 git@github.com:shop1189/lianghuaxitong.git）时使用
# - 密钥类仍由 .gitignore 排除，不会进仓库
#
# 环境变量：
#   LONGXIA_GIT_BACKUP_COMMIT=1  若有未提交改动，先 git add -A 再提交（尊重 .gitignore），再拉推
#   GIT_SYNC_AUTO_STASH=1        若仍无法快进（极少见），先 stash 再拉推再 pop
#   LONGXIA_GIT_BLOCK_MISSING_MAX  自动提交前：若 `git ls-files -d` 缺失数超过该阈值则中止（默认 5；设 0 关闭）
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
mkdir -p "$REPO/logs"
LOCK="$REPO/logs/github_sync.lock"
exec 200>"$LOCK"
if ! flock -n 200; then
  echo "$(date -Is) skip: another github_bidirectional_sync is running"
  exit 0
fi

COMMIT_MODE="${LONGXIA_GIT_BACKUP_COMMIT:-0}"
AUTO_STASH="${GIT_SYNC_AUTO_STASH:-0}"

if ! git rev-parse HEAD &>/dev/null; then
  echo "not a git repository" >&2
  exit 1
fi

BRANCH="$(git branch --show-current 2>/dev/null || echo main)"
REMOTE="${LONGXIA_GIT_REMOTE:-origin}"

_git_dirty() {
  [[ -n "$(git status --porcelain 2>/dev/null)" ]]
}

_abort_if_mass_worktree_loss() {
  # 防止「磁盘上跟踪文件被批量删掉」时仍执行 git add -A 把删除提交进 main（致命）
  local max="${LONGXIA_GIT_BLOCK_MISSING_MAX:-5}"
  [[ "${max}" =~ ^[0-9]+$ ]] || max=5
  if [[ "${max}" -eq 0 ]]; then
    return 0
  fi
  local n
  n="$(git ls-files -d 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${n}" -gt "${max}" ]]; then
    {
      echo "$(date -Is) ABORT auto-commit: ${n} tracked files missing from disk (git ls-files -d); max=${max}"
      echo "Run: git status && git restore --source=HEAD -- .   (或从备份/tag 恢复)"
    } | tee -a "$REPO/logs/github_sync.log" >&2
    exit 1
  fi
}

if _git_dirty && [[ "$COMMIT_MODE" == "1" ]]; then
  _abort_if_mass_worktree_loss
  git add -A
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "chore(backup): auto sync $(date -u +%Y-%m-%dT%H:%M:%SZ)" || true
  fi
fi

if _git_dirty && [[ "$AUTO_STASH" == "1" ]]; then
  git stash push -u -m "github_sync $(date -Is)" || true
  STASHED=1
elif _git_dirty && [[ "$COMMIT_MODE" != "1" ]]; then
  echo "$(date -Is) 工作区有未提交改动，跳过同步。可："
  echo "  LONGXIA_GIT_BACKUP_COMMIT=1 $0   # 先提交再拉推"
  echo "  GIT_SYNC_AUTO_STASH=1 $0         # 或临时 stash"
  exit 2
fi

git fetch "$REMOTE"
if ! git pull --no-edit "$REMOTE" "$BRANCH"; then
  echo "git pull 失败，请本地处理冲突后重试。" >&2
  exit 1
fi

if ! git push "$REMOTE" "$BRANCH"; then
  echo "git push 失败，请检查 SSH 密钥与 GitHub 权限。" >&2
  exit 1
fi

if [[ "${STASHED:-0}" == "1" ]]; then
  git stash pop || echo "warn: stash pop had conflicts, check git stash list"
fi

echo "$(date -Is) OK: synced $REMOTE/$BRANCH"
