#!/bin/bash
# 个人站每日同步：生成公开版阅读目录 → GitHub 备份推送 → Cloudflare Pages 部署
# 两个 token 只从 ~/.config/laowang-opc/ 下 600 权限文件读取，绝不打印到输出
cd ~/workspace/laowang-opc || exit 1

echo "== 1/3 生成公开版目录 =="
python3 build_reading.py || echo "WARN: build_reading.py 失败"

echo "== 2/3 GitHub 备份推送 =="
if [ -n "$(git status --porcelain reading/ 2>/dev/null)" ]; then
  git add reading/
  git -c user.name="laowang" -c user.email="noreply@laowang-opc.com" commit -qm "阅读目录 $(date +%F)" 2>/dev/null
  git config credential.https://github.com.helper '!f() { echo "username=wzhmaggie25-rgb"; echo "password=$LAOWANG_PAT"; }; f'
  if LAOWANG_PAT=$(cat ~/.config/laowang-opc/github-pat) git push origin main -q 2>/dev/null; then
    echo "github 推送成功"
  else
    echo "WARN: github 推送失败"
  fi
  git config --unset credential.https://github.com.helper 2>/dev/null
else
  echo "无新内容，跳过推送"
fi

echo "== 3/3 Cloudflare Pages 部署 =="
python3 deploy.py || echo "WARN: deploy.py 失败"
echo "同步完成"
