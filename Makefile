# 個人資產變化紀錄 —— 常用指令入口
# 用法： make            （列出所有指令）
#        make preview / make test / make push / make release …

PYTHON := python3
NODE   := node
CLASP  := clasp
# 部署 ID 從個人的 .clasp.json 讀（clasp 會忽略這個它不認識的欄位）；沒有就留空
DEPLOY_ID := $(shell $(NODE) -p "require('./.clasp.json').deploymentId||''" 2>/dev/null)
# 供 GAS 版本描述用：git 版本（tag/short SHA，含 -dirty）與最新 commit 標題
GIT_DESC    := $(shell git describe --tags --always --dirty 2>/dev/null)
GIT_SUBJECT := $(shell git log -1 --pretty=%s 2>/dev/null)

.DEFAULT_GOAL := help
.PHONY: help setup login convert preview test push release list-deploys clean

help: ## 顯示可用指令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## 安裝相依工具（clasp）並檢查環境
	@command -v $(PYTHON) >/dev/null || { echo "✗ 需要 python3"; exit 1; }
	@command -v $(NODE)   >/dev/null || { echo "✗ 需要 node";    exit 1; }
	npm install -g @google/clasp
	@echo "✓ 完成。接著： make login → make push → make release"

login: ## 登入 Google（clasp，會開瀏覽器授權）
	$(CLASP) login

convert: ## 由 import_data/source.plist 產生 data/*.csv（含恆等式檢查）
	$(PYTHON) tools/convert.py

preview: convert ## 產生並開啟本機預覽（免部署）
	$(NODE) tools/make_preview.js
	@command -v open >/dev/null 2>&1 && open preview/index.html \
		|| echo "→ 請用瀏覽器開啟 preview/index.html"

test: ## 執行 Ledger 單元測試
	$(NODE) --test

push: ## 上傳 src/ 到 Apps Script
	$(CLASP) push --force

list-deploys: ## 列出現有部署（用來找 deploymentId）
	$(CLASP) list-deployments

release: test push ## 測試→上傳→更新既有部署（版本描述自動帶 git commit）
ifeq ($(DEPLOY_ID),)
	@echo "✗ .clasp.json 找不到 deploymentId。"
	@echo "  先執行 'make list-deploys' 取得 ID，再把它加進 .clasp.json："
	@echo '      "deploymentId": "AKfycb..."'
	@exit 1
else
	@case "$(GIT_DESC)" in *-dirty) \
		echo "⚠️  工作目錄有未提交變更，線上版本將對不回單一 commit（描述含 -dirty）";; esac
	$(CLASP) update-deployment -d "$(GIT_DESC) — $(GIT_SUBJECT)" $(DEPLOY_ID)
	@echo "✓ 已發佈：$(GIT_DESC) — $(GIT_SUBJECT)"
endif

clean: ## 清除產生物（preview/、__pycache__）
	rm -rf preview __pycache__ tools/__pycache__
