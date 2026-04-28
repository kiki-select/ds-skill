-- 主查询：经典模式各日 DAU
-- 实体粒度：gameserver_login 是单玩家事件，pid 直接 count distinct
select `#dt`,
        count(distinct pid) as dau
  from events
  where `#event` = 'gameserver_login'
    and `#dt` between '2026-04-14' and '2026-04-20'
    and login_type = 0
  group by 1
  order by 1
