# 交大网络中心待咨询清单（jCloud 部署前置）

> 用途：在 `socialeval.sjtu.edu.cn` 域名申请流程中，向学校网络信息中心一并确认下列
> 事项。这些问题的答案决定 Caddy 自动 HTTPS 能否在 VM 上独立完成，还是必须改走
> 学校统一反代。记录日期：2026-07-26。
>
> 本文件只列问题与替代方案的临时决定，不含任何凭据值。

## 1. 必须向网络中心确认的三件事

### Q1. DNS A 记录指向
- 问题：`socialeval.sjtu.edu.cn` 的 A 记录能否**直接指向 jCloud VM 的公网 IP**？
  还是强制指向学校统一反向代理 / WAF 网关？
- 影响：若可直接指向 VM，Caddy 在 VM 上自管 443 即可；若强制走学校反代，
  Caddy 不得暴露公网 443，改由学校反代终止 TLS、向 VM 转 HTTP。
- 期望答案：可直接指向 jCloud VM 公网 IP。

### Q2. 入站 80/443 端口开放方式
- 问题：jCloud VM 的公网入站 80/443 是在 **jCloud 控制台自助开安全组**，
  还是要走学校网络中心统一防火墙审批？
- 影响：自助开则无需网络中心二次介入；走统一防火墙则需要他们开通（一次性）。
- 期望答案：jCloud 控制台可自助开放 80/443。
- 备注：`docker-compose.prod.yml` 已约束 PostgreSQL/Redis 不映射公网端口，
  公网只暴露 Caddy 的 80/443。

### Q3. 是否强制对外 Web 走学校统一反代 / WAF
- 问题：交大是否规定所有 `*.sjtu.edu.cn` 对外 Web 必须经过学校统一反向代理 /
  WAF 网关终止 TLS（出于 WAF、合规、统一日志）？
- 影响：
  - 若**否**：Caddy 自动向 Let's Encrypt 申请并续期证书，HSTS/CSP/X-Frame-Options
    等安全头由 Caddy 下发，全流程不需要再找网络中心。
  - 若**是**：Caddy 只监听内部 HTTP，TLS 由学校反代终止；安全头要么由学校反代
    下发，要么依赖其透传（需确认是否透传 `Strict-Transport-Security`、
    `Content-Security-Policy` 等）；`SESSION_HTTPS_ONLY`、`X-Forwarded-*` 仍能
    正常工作，因为 `docker-compose.prod.yml` 已开
    `--proxy-headers --forwarded-allow-ips=*`。
- 期望答案：不强制走学校反代，允许 VM 自管 TLS。

## 2. 证书签发与续期

- 结论：**不需要网络中心**。Caddy + Let's Encrypt 全自动，LE 是公共 CA，验证通过
  即签发并自动续期，不经过学校 CA、不需要学校审批或上传证书。
- 前置：Q1、Q2 满足且 Q3 为"否"后，只要在 `.env.production` 填入
  `APP_DOMAIN=socialeval.sjtu.edu.cn`、`PUBLIC_BASE_URL=https://socialeval.sjtu.edu.cn`，
  Caddy 启动后自动签证书。

## 3. 当前临时替代与风险（已写入 `.env.production`，仅本机/联调用，不对外）

### 3.1 用 IP 替代域名
- 门禁代码（`src/core/production.py`）只拒绝 `localhost`/`127.0.0.1`、HTTP、
  占位密钥；裸公网 IP 在代码层不拦，但 `PUBLIC_BASE_URL` 必须 `https://`。
- 风险：Caddy 对裸 IP 无法自动签 Let's Encrypt 证书，会回落到内部自签证书，
  浏览器报错；只适合本地联调，不适合给期刊编辑用。
- 建议：域名批下来之前**不对外上线**；如需联调可用临时 DNS 名字指向 IP，
  或用 `tls internal` 自签仅自己测试。
- 切换正式域名后的影响：
  - `SESSION_HTTPS_ONLY` cookie 域会变，已登录用户需重登；
  - 邀请 / 密码重置链接 host 取自 `PUBLIC_BASE_URL`，旧邮件里链接 host 会失效，
    但令牌在 DB 以哈希 fragment 存储，换域名后用新 host 拼同样 fragment 仍可激活
    （只要令牌未过期）。故**正式域名定下来后再发任何对外邀请邮件**。

### 3.2 用个人邮箱替代 SMTP_FROM
- 门禁代码只校验 `smtp_host`、`smtp_from` 非空，不校验是否个人邮箱，代码层通过。
- 风险：deliverability 差，易被期刊编辑邮箱判垃圾。
- 建议：这段时间只给自己 / 测试账号发邀请，**不给真实期刊编辑发**；
  切换学校邮箱不影响 `FIELD_ENCRYPTION_KEY`（已加密令牌仍可解密），低风险替代。

## 4. 上线前还需确认的非代码项（项目红线，超出网络中心范围）

- 数据保留默认值（稿件 365 天 / 审计 1095 天）需期刊与学校确认。
- 模型供应商对未公开稿件的数据处理条款与学校授权范围。
- 生产仍指向模型集 `six-dimension-v1`；`six-dimension-v2-candidate` 状态为
  `candidate-unvalidated`，未完成结果复核 / 编辑抽样 / 验证签字前不得切生产。

## 5. 后续动作

1. 域名申请流程中向网络中心提交 Q1–Q3，取书面答复。
2. 拿到答复后更新本文件第 1 节，并据 Q3 答案决定 Caddy 自管 TLS 还是改走学校反代。
3. 域名解析生效 + 80/443 开放后，在 jCloud VM 上跑
   `scripts/check_production_readiness.py`（不得用 `docker-compose.test.yml` 绕过），
   再按 `docs/deployment/CURRENT-HANDOFF.md §6` 的 12 步推进。
