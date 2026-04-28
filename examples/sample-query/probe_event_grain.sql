-- 探查：看一条 gameserver_login 事件长什么样
-- 目的：识别实体粒度（pid 是数值 → 单实体事件，可直接 count(distinct pid)）
select *
  from events
  where `#event` = 'gameserver_login'
    and `#dt` = '2026-04-20'
  limit 3
