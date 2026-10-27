# wereply 服务集成契约

本次变更替换 `new-messages` 摘要接口，并将 `history --format json` 的 `messages`
从展示字符串改为对象。调用方必须按新结构升级。

```bash
wecli new-messages --limit 100
wecli new-messages --cursor "$CURSOR" --limit 100
wecli history wxid_example --format json --limit 50
wecli doctor --format json
```

消息对象提供 `message_id`、`account_id`、`chat_id`、`sender_id`、`is_self`、
`timestamp`（Unix 秒）、`type`（微信原始整数类型）、`text`、`content`、`source`、`local_id`。
`text` 保留完整正文，群聊的发送者前缀被移除；`content` 保留解压后的原始内容，
非文本消息可能是 XML，不会假装已经解析为媒体或引用消息结构。
无法解析发送者时 `sender_id` 和 `is_self` 为 null；调用方不能把 null 当成非本人。
账号自身无法识别或任意数据库读取失败时，整页失败，不返回部分成功游标。

省略游标从所有本地历史开始，不仅限未读；不会自动跳到当前时刻。
页面按数据库、会话表、local_id 遍历，不保证跨会话时间顺序。
`has_more` 为 true 时继续取下一页；false 时保存游标并稍后轮询。
游标包含每个来源的位置，不是一个时间戳，因此同秒多条和晚到的旧时间戳不被忽略。

消费者应在同一个事务中保存消息/任务、按 `message_id` 去重并更新 `next_cursor`。
只有事务成功后才使用新游标。重启使用持久化游标；输出失败或进程中断重用旧游标。
这是至少一次读取，副作用也需要幂等控制，不提供恰好一次送达。
多个独立消费者各自保存游标；同一消费者不能无协调地覆盖共享游标。

ID 由规范账号目录、数据库相对路径、会话表和 local_id 派生。
契约基于微信在每张消息表中以递增 local_id 追加；不以消息时间作为水位。
目录搬迁、库重建/迁移、local_id 复用不在稳定 ID 保证内。
检测到来源消失或最大 local_id 回退会报错，需人工恢复；不能检测所有删库后复用 ID 情况。
尚未被轮询读取就已从微信本地库删除的消息无法恢复；不包含数据库里尚未写入的消息。
游标绑定账号目录，切换配置后拒绝复用。配置仍指向旧账号时可以读取旧数据，
因此服务还应核对 `doctor` 的运行账号匹配结果，并绑定预期 `account_id`。

解密快照按账号隔离且每个进程独立创建，不共享可写 SQLite 文件；读取时检测源库变化，
遇到变化错误应以原游标重试。历史 JSON 会遍历该聊天全部记录后排序，长历史查询成本较高，
常驻采集应使用增量接口。

发送的 UUID、持久化状态、串行锁、退出码和异常核对见[发送文档](sending.md)。
`recorded` 表示本人本地记录确认，不表示服务器送达；`failed` 表示点击前失败；
`unknown` 表示不能确认，禁止无条件自动重发。
