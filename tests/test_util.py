from token_tracker.adapters.util import project_from_cwd


def test_project_from_cwd_git_root(tmp_path):
    # 仓库根 + 子目录都归到仓库根（向上找 .git）
    repo = tmp_path / "infohunter"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "official"
    sub.mkdir()
    assert project_from_cwd(str(repo)) == "infohunter"
    assert project_from_cwd(str(sub)) == "infohunter"


def test_project_from_cwd_subdir_deleted(tmp_path):
    # 子目录已删、仓库根还在 → dirname 向上仍命中 .git，归到仓库根
    repo = tmp_path / "infohunter"
    (repo / ".git").mkdir(parents=True)
    gone = repo / "official"  # 故意不创建，模拟已删
    assert project_from_cwd(str(gone)) == "infohunter"


def test_project_from_cwd_git_file(tmp_path):
    # worktree / submodule 的 .git 是文件而非目录，也应识别为仓库根
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere\n")
    assert project_from_cwd(str(repo / "sub")) == "myrepo"


def test_project_from_cwd_non_git_fallback(tmp_path):
    # 非 git 目录 → 回退最后一段
    d = tmp_path / "loose" / "folder"
    d.mkdir(parents=True)
    assert project_from_cwd(str(d)) == "folder"
