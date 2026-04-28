-- 抽样校验：抽 1 个 pid 在 2026-04-20 的所有 login 事件
-- 期望：该 pid 在该日 distinct pid count = 1（即贡献 1 个 DAU），与主查询那一行的子集对得上
-- 用法：从主查询结果挑某天 dau 数最高的服务器，再随机挑 1 个 pid 替换 <挑出的 pid>
select pid, `#time`, login_type
  from events
  where `#event` = 'gameserver_login'
    and `#dt` = '2026-04-20'
    and pid = <挑出的 pid>
  order by `#time`
