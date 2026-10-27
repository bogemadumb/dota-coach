# Механики Dota 2, часть A — справочник для AI-тренера (патч 7.41f)

Патч: **7.41f**, вышел 2026-09-15 (метка в [официальном JSON](https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english)). Справочник собран 2026-10-01.

## Как читать источники и приоритеты

- Официальные заметки (JSON): [7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english), [7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english), [7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english), [7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english), [7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english), [7.41a](https://www.dota2.com/datafeed/patchnotes?version=7.41a&language=english), [7.41b](https://www.dota2.com/datafeed/patchnotes?version=7.41b&language=english), [7.41c](https://www.dota2.com/datafeed/patchnotes?version=7.41c&language=english), [7.41d](https://www.dota2.com/datafeed/patchnotes?version=7.41d&language=english), [7.41e](https://www.dota2.com/datafeed/patchnotes?version=7.41e&language=english), [7.41f](https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english). Ссылки ниже подписаны «оф. 7.xx».
- Текущие числа предметов взяты из живого официального датафида `itemdata` (ссылка с `item_id` у каждого предмета; он отражает 7.41f: например, цена Heaven's Halberd 3300 совпадает с заметкой 7.41f). Подпись «датафид-предмет».
- Базовые статы героев — из датафида `herodata` по всем 127 героям (подпись «датафид-герои»; я сам вычел вклад атрибутов — это расчёт, а не цитата).
- Liquipedia — для общих правил, которых нет в заметках. Страницы Liquipedia местами устарели (см. конфликты в конце файла). При конфликте приоритет у официальных заметок/датафида.
- Пометка `(не проверено для 7.41f)` — факт не подтверждён на текущем патче.
- Терминология с 7.33: **Spell Immunity** (иммунитет к заклинаниям) у BKB заменён на **Debuff Immunity** (иммунитет к дебаффам); см. раздел 5.
- Важные глобальные изменения последних патчей: в 7.41 удалены Facets (грани) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)); в 7.39 Lifesteal Amplification и Spell Lifesteal Amplification заменены на Health Restoration ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)); в 7.41 Health Restoration расширен на все виды лечения (раздел 10).

---

## 1. Атрибуты

### Правила

- 1 Strength (сила) даёт **+22 к максимальному HP** ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes); подтверждено расчётом по [датафид-герои, Juggernaut](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8): 20 силы → 560 HP при базе 120; оф. рост с 20 до 22 в [7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
- 1 Strength даёт **+0.1 к регенерации HP** ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes); подтверждено расчётом по [датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8): у Juggernaut 2.5 = 20×0.1 + 0.5).
- Strength **не даёт** магического сопротивления: бонус 0.08% за силу убран в 7.26 ([Liquipedia Strength](https://liquipedia.net/dota2/Strength)); в заметках 7.33–7.41f его возврата нет ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english), [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- 1 Agility (ловкость) даёт **+1 к скорости атаки** (attack speed) ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes)).
- 1 Agility даёт **+0.167 (=1/6) к базовой броне** ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes); подтверждено расчётом: у Juggernaut броня 5.333 при 32 ловкости, [датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8)).
- 1 Intelligence (интеллект) даёт **+12 к максимальной мане** ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes); расчёт по [датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8): 243 = 75 + 14×12).
- 1 Intelligence даёт **+0.05 к регенерации маны** ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes); расчёт по [датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8): 0.7 = 14×0.05 + 0).
- 1 Intelligence даёт **+0.1% к базовому магическому сопротивлению** (то есть 10 Int = +1%) — официально введено в 7.33: «Intelligence now grants 0.1% base Magic Resistance per point» ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english); [Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)). Это единственный атрибутный бонус к магическому сопротивлению в 7.41f.
- **Spell amplification (усиление заклинаний) от Intelligence в 7.41f не найдено**: ни в Liquipedia (список бонусов Int: мана, реген маны, магсопротивление), ни в заметках 7.33–7.41f ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes), [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)). Это вывод по отсутствию данных, не прямое подтверждение.
- **Основной атрибут (primary attribute)**: каждая единица основного атрибута даёт **+1 к основному урону атаки** ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes)). Остальные два атрибута урона не дают.
- **Universal-герои**: каждая единица **каждого** из трёх атрибутов даёт **+0.45 к основному урону** — понижено с 0.7 до 0.45 в 7.38 ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)); на 7.41 значение 0.45 всё ещё актуально: заметка про Void Spirit «increased from 0.45 to 0.5175» ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)); [Liquipedia Universal](https://liquipedia.net/dota2/Universal) тоже 0.45.
- В датафиде у Universal-героев `damage_min/max` — это голый базовый урон без бонуса от атрибутов (расчёт по [датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8) на нескольких героях; Bane: 24 при сумме атрибутов 69). Для реального урона надо добавлять 0.45×(Str+Agi+Int).
- **Базовые значения** (расчёт по всем 127 героям из [датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8); база = итоговый стат минус вклад атрибутов):
  - Базовое HP: **120** у всех 127 героев (оф. подтверждение: «Base Hero HP decreased from 200 to 120», [оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
  - Базовая мана: **75** у 125 героев; Huskar 0, Ogre Magi 120 ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8), расчёт).
  - Базовый реген HP: зависит от героя; чаще всего **0.25** (70 героев), затем 1.0 и 0.5 (по 15), 0.75 (8); крайние значения −0.5 и 3.0 ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8), расчёт).
  - Базовый реген маны: у 95 героев **0**, у 19 героев 0.5, остальные 0.25–0.75; у одного −1.0 ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8), расчёт).
  - Базовая броня (без вклада ловкости): зависит от героя; чаще всего **0** (53 героя), 1 (35), 2 (17), −1 (13), −2 (4); максимум 6 ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8), расчёт). Заметки 7.41 содержат 8 точечных правок базовой брони героев ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
  - Базовое магическое сопротивление: **25% у всех героев** ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8): поле `magic_resistance`=25 у всех 127; [Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)).
  - Базовое время атаки (BAT): у 92 из 127 героев **1.7**; остальные 1.4–2.0 (Anti-Mage и Juggernaut 1.4, Hoodwink 2.0) ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8), поле `attack_rate`).
  - Базовая скорость атаки: 100 у большинства героев, у части героев своя (85–125) ([Liquipedia Attack Speed](https://liquipedia.net/dota2/Attack_Speed)) `(не проверено для 7.41f)` по конкретным героям.
- Способность «Attribute Bonus» (кнопка +атрибуты под талантами): по Liquipedia даёт +2 ко всем атрибутам за уровень, максимум 7 уровней, доступна с 2-го уровня героя ([Liquipedia Attributes](https://liquipedia.net/dota2/Attributes); [оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english) — «со 2-го уровня»; [оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english) — «all +2 All Attributes bonuses skilled by level 22»). **Датафид показывает иначе** (`attribute_bonus_all`=4, `max_level`=4, плюс бонусы к скорости/атаке/броне на уровнях) ([датафид-способность 5002](https://www.dota2.com/datafeed/abilitydata?language=english&ability_id=5002)) — расхождение не объяснено заметками `(не проверено для 7.41f)`.
- Таланты с 7.40 не требуют очков умений: они берутся отдельными очками на уровнях 10, 15, 20, 25, 27, 28, 29, 30 ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); значит максимальный уровень героя 30.
- Facets (грани) удалены в 7.41; innate-способности больше не масштабируются от уровня других способностей ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- Иллюзии получают атрибуты и вторичные бонусы от них ([Liquipedia Armor](https://liquipedia.net/dota2/Armor), [Liquipedia Attributes](https://liquipedia.net/dota2/Attributes)).

### Частые ошибки

- «Сила даёт магическое сопротивление» — нет, с 7.26 не даёт.
- «Интеллект даёт усиление заклинаний» — в 7.41f нет; интеллект даёт ману, реген маны и +0.1% базового магсопротивления.
- «Базовое магическое сопротивление 33%/35%» — у героев 25% (плюс 0.1% за каждую единицу Int).
- «Universal даёт 0.6/0.7 урона за атрибут» — устарело, сейчас 0.45.
- «Базовое HP героя 200» — устарело, 120.
- «У всех героев BAT 1.7» — у 35 из 127 другой; скорость атаки надо считать с учётом BAT.
- «Урон универсала в датафиде уже включает атрибуты» — нет, это голая база.

### Что это значит для покупок

- Ghost Scepter, Circlet/Crown/Diadem/Ultimate Orb и подобные «все атрибуты» предметы для Universal дают урон +0.45 за очко каждого атрибута, для основных героев — только +1 за очко основного атрибута ([Liquipedia Universal](https://liquipedia.net/dota2/Universal)).
- Покупка предметов на Strength: +22 HP и +0.1 регена за очко; на Intelligence: +12 маны, +0.05 регена маны, +0.1% магсопротивления; на Agility: +1 AS и +1/6 брони за очко (расчёт по числам выше).
- Intelligence-предметы не усиливают заклинания сами по себе (нет spell amp от Int).

---

## 2. Броня (Armor)

### Правила

- Формула снижения физического урона: **множитель урона = 1 − 0.06×A / (1 + 0.06×|A|)**, где A — суммарная броня; введена в 7.27 ([оф. 7.27](https://www.dota2.com/datafeed/patchnotes?version=7.27&language=english); [Liquipedia Armor](https://liquipedia.net/dota2/Armor)).
- Примеры расчёта: 10 брони → урон ×0.625 (−37.5%); 20 → ×0.4545 (−54.5%); 30 → ×0.357 (−64.3%); −10 → ×1.375 (+37.5%) (расчёт по формуле выше).
- Каждая единица положительной брони добавляет эффективного HP около 6% от базового количества HP (EHP = HP×(1+0.06×A) при A ≥ 0) ([Liquipedia Armor](https://liquipedia.net/dota2/Armor)).
- Отрицательная броня **увеличивает** получаемый физический урон; множитель ограничен сверху значением 2 (при A → −∞), снизу 0 ([Liquipedia Armor](https://liquipedia.net/dota2/Armor)).
- Броня влияет на физический урон от атак и физический урон от способностей; магический и чистый урон она не снижает ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- Броня героя = базовая броня + Agi/6 (основная, «белая» цифра) + бонусная («зелёная»); большинство предметов и способностей меняют именно бонусную броню ([Liquipedia Armor](https://liquipedia.net/dota2/Armor)).
- Эффекты «negation» (Elder Titan Natural Order, Drow Marksmanship, Clinkz Infernal Shred) уменьшают **основную** броню, но не бонусную; пример Liquipedia: основная 17.5 × (1−80%) + бонус 7 = 10.5 ([Liquipedia Armor](https://liquipedia.net/dota2/Armor)) `(не проверено для 7.41f)` по текущим значениям умений.
- Снижающие броню предметы (значения из [датафида-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=168)): Desolator −6 на 7 с; Stygian Desolator −13 на 7 с ([id 292](https://www.dota2.com/datafeed/itemdata?language=english&item_id=292)); Orb of Corrosion −2 на 3 с ([id 569](https://www.dota2.com/datafeed/itemdata?language=english&item_id=569)); эффект работает по зданиям (Desolator/Stygian).
- Эти снижения **не суммируются** между собой: Orb of Corrosion — «Armor reduction does not stack with its components, Desolator, or Stygian Desolator»; Orb of Blight — «…Desolator, or Stygian Desolator» ([датафид-предмет Orb of Corrosion](https://www.dota2.com/datafeed/itemdata?language=english&item_id=569)).
- Армор-коррупция от талантов (атаки снижают броню на 2.5–5 на 10 с) стакается независимо от других источников; повторное применение обновляет длительность ([Liquipedia Armor](https://liquipedia.net/dota2/Armor)) `(не проверено для 7.41f)`.
- Берсерк Mask of Madness снижает **собственную** броню на 7 (7.41: было 8) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english); [датафид-предмет](https://www.dota2.com/datafeed/itemdata?language=english&item_id=172)).
- Броня зданий/Tormentor/Roshan: у Roshan базовая броня 30, у Tormentor 20 ([Liquipedia Armor](https://liquipedia.net/dota2/Armor); оф. [7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english) для обоих чисел) `(не проверено для 7.41f)`.
- Броня крипов и зданий: «Reinforced», «Piercing», «Runty» — модификаторы типа атаки, которые меняют урон по героям/негероям отдельно от брони ([Liquipedia Armor](https://liquipedia.net/dota2/Armor), 7.31) `(не проверено для 7.41f)`.
- Предметы с большой бронёй (по [датафид-предметам](https://www.dota2.com/datafeed/itemdata?language=english&item_id=119), Shiva's Guard; остальные — id в том же датафиде): Platemail +10, Shiva's Guard +17, Assault Cuirass +10, Heaven's Halberd +9, Splintmail +7, Lotus Orb +10, Nullifier +10, Blade Mail +7, Crimson Guard +6.

### Частые ошибки

- «Броня снижает урон на 6% за очко линейно» — только для малых значений; формула гиперболическая (убывающая отдача).
- «Броня снижает магический/чистый урон» — нет.
- «Снижения брони от Desolator, Stygian и Orb of Corrosion складываются» — нет, не стакаются между собой.
- «Negation режет всю броню» — только основную часть (по Liquipedia).
- «Броня Mask of Madness Berserk — дебафф на врага» — это штраф самому владельцу.

### Что это значит для покупок

- Desolator/Stygian — самый сильный источник −брони (−6 / −13 на 7 с); Orb of Corrosion/Blight рядом с ними не добавляют снижения.
- Из-за гиперболической формулы дополнительные очки брони эффективнее на низкой броне, чем на высокой; для кора с 25+ брони покупка ещё +10 даёт меньший относительный прирост EHP, чем +10 при 5 броне (расчёт по формуле).

---

## 3. Магическое сопротивление (Magic Resistance)

### Правила

- База героя **25%**, плюс **0.1% за каждую единицу Int** ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8); [оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
- Бонусы от предметов, способностей и талантов **перемножаются** (стакаются мультипликативно): множитель магурона = (1−база)×Π(1−бонус_i) ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)); у Cloak/Shawl прямо написано «Stacks multiplicatively with other sources of magic resistance» ([датафид-предмет Cloak](https://www.dota2.com/datafeed/itemdata?language=english&item_id=31)).
- Пример: база 25% + Cloak 18% → итог 1−0.75×0.82 = **38.5%** (расчёт по формуле выше); база + Cloak + Glimmer (20%) → 1−0.75×0.82×0.80 = 50.8%.
- Снижение магсопротивления (Ancient Apparition Ice Vortex, Skywrath Ancient Seal, Keeper Solar Bind, Shadow Fiend Requiem и др.) входит в тот же мультипликативный расчёт ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)).
- Источники **эфирности** (Ethereal Blade, Ghost Scepter, Necrophos Ghost Shroud, Pugna Decrepify, Leshrac Nihilism) увеличивают получаемый магурон; несколько эфирных эффектов не стакаются — берётся наибольший ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)). С 7.39e эфирная форма не накладывается на цель с Debuff Immunity ([оф. 7.39e](https://www.dota2.com/datafeed/patchnotes?version=7.39e&language=english)).
- Только Elder Titan Natural Order (и его Astral Spirit) умеет «обнулять» **базовое** магсопротивление (множитель на базу, остальные источники не затрагивает) ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)) `(не проверено для 7.41f)`.
- Порядок расчёта магурона: блок → магсопротивление → магический барьер (Pipe, Glimmer, Aphotic Shield) → прочие множители ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance); оф. 7.33: «Magic barriers are now calculated after magic resistance reductions» ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english))).
- Сопротивление 100% **не** равно спелл-иммунитету или иммунитету к дебаффам: дебаффы всё равно накладываются, только урон нулевой ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)).
- Debuff Immunity (BKB и др.) даёт дополнительное магсопротивление **как отдельный множитель**: BKB 60% (с 7.35c, было 50%) ([датафид-предмет BKB](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116); [оф. 7.35c](https://www.dota2.com/datafeed/patchnotes?version=7.35c&language=english)). Заклинания, пробивающие Debuff Immunity, игнорируют этот бонус ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
- Магсопротивление иллюзий не работает (все модификаторы = 0) ([Liquipedia Magic Resistance](https://liquipedia.net/dota2/Magic_Resistance)) `(не проверено для 7.41f)`.
- Предметы (значения из [датафида-предметов](https://www.dota2.com/datafeed/itemdata?language=english&item_id=31)): Cloak 18% (7.41: −2), Shawl 10%, Glimmer Cape 20% ([id 254](https://www.dota2.com/datafeed/itemdata?language=english&item_id=254); 7.39: 25→20), Mage Slayer 18% ([id 598](https://www.dota2.com/datafeed/itemdata?language=english&item_id=598); 7.41b: 20→18), Consecrated Wraps 12% ([id 1854](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1854); 7.41a: 15→12), Pipe of Insight 20% самому + 8% аура союзникам ([id 90](https://www.dota2.com/datafeed/itemdata?language=english&item_id=90)). Eternal Shroud (20% + 3.5% за стак) **убран из игры в 7.41** («Item removed from the game», [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)): запись осталась в датафиде, но предмет не продаётся.

### Частые ошибки

- «Магсопротивление складывается» — нет, множится.
- «25% базы плюс 18% Cloak = 43%» — это 38.5%.
- «BKB даёт неуязвимость к магии» — BKB даёт 60% магсопротивления плюс иммунитет к дебаффам; магурон проходит, но сниженный; пробивающие заклинания игнорируют даже эти 60%.
- «Сила даёт магсопротивление» — нет с 7.26.
- «100% магсопротивления защищает от оглушения» — нет.

### Что это значит для покупок

- Первый Cloak/Shawl эффективнее всего (мультипликативная формула: рост снижения магурона убывает по мере накопления).
- Pipe/Glimmer полезны не только процентами: они ещё дают магический барьер, считаемый **после** магсопротивления (Eternal Shroud убран в 7.41).
- Против Debuff-пробивающих ультов (например Abyssal Overwhelm) BKB не помогает вообще.

---

## 4. Типы урона и флаги

### Правила

- Три основных типа: физический, магический, чистый (pure) ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- **Физический**: снижается бронёй и блоком урона (damage block); не проходит по эфирным целям; уклонение (evasion/blind) может заставить промахнуться по атаке ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- **Магический**: снижается магсопротивлением и магическими барьерами; по эфирным целям усиливается ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- **Чистый (pure)**: не снижается бронёй и магсопротивлением, не получает блок; на него действуют общие уменьшители урона (например Spectre Dispersion, Bristleback) ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)). Не влияет на неуязвимые цели.
- Чистый урон **пробивает** спелл-иммунитет по урону (иммунитет сам по себе урон не блокирует), но заклинание с чистым уроном может быть не в состоянии таргетить такую цель (Tinker Laser) ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types), [Liquipedia Spell Immunity](https://liquipedia.net/dota2/Spell_Immunity)).
- **Debuff Immunity даёт 100% защиту от чистого урона и отражённого урона** (только от источников, не пробивающих иммунитет к дебаффам); физический урон иммунитет не снижает ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english); [Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- **HP Removal** (флаг DOTA_DAMAGE_FLAG_HPLOSS): урон игнорирует и не вызывает большинство on-damage эффектов (не прерывает Blink Dagger, не отменяет расходники), не усиливается и не ослабляется общими модификаторами, не даёт spell lifesteal; но может убить и подчиняется классу урона (магсопротивление всё ещё применяется) ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)). Примеры: Spectre Dispersion, Necrophos Heartstopper Aura, Orb of Venom Poison Attack (оф. упоминание Orb of Venom и Heartstopper в заметках: [оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- **No-reflection**: урон, который не может быть отражён обратно (Blade Mail Damage Return, Dispersion, Corrosive Skin, Fatal Bonds и др.) — защита от бесконечных петель ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)). Официально с 7.41: «Reflected damage cannot be reflected back», «Lifesteal and Spell Lifesteal don't apply to reflected damage», «Reflected damage doesn't affect Debuff Immune units» ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- Источники отражённого урона (оф. список 7.41): Tormentor Reflect, Blade Mail (актив и пассив), Chipped Vest, Rattlecage, Axe Counter Helix, Bristleback Quill Spray от Bristleback, Centaur Retaliate, Nyx Spiked Carapace, QoP Scream of Pain, Razor Storm Surge, Shadow Demon Disseminate, Spectre Dispersion, Tidehunter Anchor Smash от Kraken Shell, Viper Corrosive Skin, Warlock Fatal Bonds ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **No-spell-lifesteal / No-spell-amplification** флаги: часть урона (Cleave, Luna Moon Glaives, Magnus Empower, Tinker/WD бонусы, Kunkka Tidebringer и др.) не даёт spell lifesteal и/или не усиливается spell amp ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- Другие флаги: **No-lethality** (урон нелетален, обычно по союзникам/самому кастеру), **No-manipulation** (игнорирует любые модификаторы урона, в том числе spell amp) ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- Мгновенное убийство (Culling Blade, Ice Blast порог и др.) не является уроном и обходит почти все модификаторы ([Liquipedia Damage Types](https://liquipedia.net/dota2/Damage_Types)).
- **Усиление заклинаний (spell amplification)**: источники «исходящего» усиления суммируются **аддитивно** между собой; «входящего» (дебаффы на цели вроде Veil of Discord, Bloodstone aura) тоже суммируются между собой; затем две группы **перемножаются**: множитель = (1 + Σисходящие) × (1 + Σвходящие) ([Liquipedia Spell Amplification](https://liquipedia.net/dota2/Spell_Amplification)). Общие уменьшители урона (Dispersion и т. п.) складываются с «входящей» группой.
- Пример Liquipedia: Bloodrage 30% + Kaya and Sange 12% − Mage Slayer 35% = 1.07 исходящий; × (1 + 0.16 Spell Weakness − 0.18 Dispersion) = 1.0486 ([Liquipedia Spell Amplification](https://liquipedia.net/dota2/Spell_Amplification)).
- Предметы-источники: Kaya 10%, Kaya and Sange 12%, Yasha and Kaya 12%, Meteor Hammer 10%, Divine Rapier (режим Transmute) 25%, Trident 30% ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=259), [Rapier](https://www.dota2.com/datafeed/itemdata?language=english&item_id=133)). Несколько предметов семейства Kaya **не стакаются** ([датафид-предмет Kaya](https://www.dota2.com/datafeed/itemdata?language=english&item_id=259): «Multiple instances of this item do not stack»; [Liquipedia Spell Amplification](https://liquipedia.net/dota2/Spell_Amplification)); несколько Divine Rapier не стакаются (оф. 7.41e: «Spell Amplification from multiple Divine Rapiers no longer stacks», [оф. 7.41e](https://www.dota2.com/datafeed/patchnotes?version=7.41e&language=english)).
- Входящее усиление: Bloodstone Spell Weakness Aura (+10% к урону заклинаний по врагам в радиусе 1200) и Veil of Discord Spell Weakness **не стакаются между собой** ([датафид-предмет Bloodstone](https://www.dota2.com/datafeed/itemdata?language=english&item_id=121): «does not stack with Veil of Discord's Spell Weakness»).
- Исходящее **снижение** спелл-урона: Mage Slayer −40% к спелл-урону носителя дебаффа ([датафид-предмет Mage Slayer](https://www.dota2.com/datafeed/itemdata?language=english&item_id=598)).
- Spell amp применяется ко всем трём типам спелл-урона (магический, физический, чистый), если у способности нет флага No-spell-amplification ([Liquipedia Spell Amplification](https://liquipedia.net/dota2/Spell_Amplification)); на HP Removal входящее усиление не действует ([там же](https://liquipedia.net/dota2/Spell_Amplification)) `(не проверено для 7.41f)` по текущему списку исключений.

### Частые ошибки

- «Spell amp (Kaya) усиливает только магический урон» — по Liquipedia он усиливает весь спелл-урон (магический, физический, чистый), кроме способностей с флагом No-spell-amplification и HP Removal.
- «Spell amp складывается с дебаффами Veil/Bloodstone в одну сумму» — нет: исходящее и входящее перемножаются.
- «Kaya + Kaya and Sange дают 22%» — нет, семейство Kaya не стакается (берётся максимум).
- «Два Divine Rapier удваивают spell amp» — нет с 7.41e.
- «Debuff Immunity блокирует физический урон» — нет, физический урон она не меняет.
- «Отражённый урон лечит» — нет, lifesteal/spell lifesteal не работают на отражённый урон.

### Что это значит для покупок

- Kaya-семейство — один слот spell amp; второй Kaya-предмет ради amp бессмысленен.
- Против героев с Debuff Immunity урон Blade Mail не проходит (отражённый урон не действует на Debuff Immune).
- Veil of Discord и Bloodstone не стакают ауру Spell Weakness: покупать оба в команду ради ауры не нужно.

---

## 5. Спелл-иммунитет и иммунитет к дебаффам (BKB и др.)

### Терминология (с 7.33)

- В 7.33 «Spell Immunity» (магический иммунитет) у BKB и ряда способностей **переработан в Debuff Immunity (иммунитет к дебаффам)** ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
- **Spell Immunity** как отдельный статус сохраняется у нейтральных/вспомогательных юнитов (варды, курьер, Undying Zombie, Plague Ward, Tombstone, Twin Gate и т. д.) и у героев во время некоторых способностей вместе с неуязвимостью (Juggernaut Omnislash/Swiftslash, Dawnbreaker Solar Guardian, Lifestealer Infest, Terrorblade Reflection illusion, Tusk Snowball) ([Liquipedia Spell Immunity](https://liquipedia.net/dota2/Spell_Immunity)).

### Правила: Debuff Immunity (BKB)

- Заклинания **можно кастовать** на цель с Debuff Immunity, даже если они её не пробивают; эффекты накладываются, но их негативное действие не работает, пока длится иммунитет; если иммунитет закончился раньше дебаффа, дебафф начинает действовать на оставшееся время ([оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english); [Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- Debuff Immunity **не снимает** уже висящие дебаффы (только временно подавляет); BKB при этом сам даёт базовый диспел при активации ([датафид-предмет BKB](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116); [Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- Подавляются: стан/сон, молчание/mute/Break, обезоруживание/слепота, циклон (цель остаётся на земле), хекс, насильственное перемещение, страх/насмешка, корни/leash, эфирность/иммунитет к атакам, замедления, снижения характеристик (скорость, броня, магсопротивление, статус-сопротивление, атрибуты, дальность), снижение лечения/реген/lifesteal, истощение маны ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- Debuff Immunity даёт **магсопротивление-бонус** (BKB 60%) и **100% иммунитет к чистому и отражённому урону** (против способностей, не пробивающих иммунитет); физический урон не меняется ([датафид-предмет BKB](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116); [оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
- Дополнительный иммунитет к потере маны (Mana Burn/Drain и т. п.), если способность не пробивает ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- Не мешает вражеской видимости (True Sight, общее зрение, раскрытие) ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- **BKB сегодня**: Avatar — базовый диспел, 60% магсопротивления, иммунитет к отражённому и чистому урону; длительность **9/8/7 с** по уровням (7.41: убран четвёртый уровень 6 с); с 7.41b длительность фиксирована и не увеличивается усилением длительности баффов ([датафид-предмет BKB](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english); [оф. 7.41b](https://www.dota2.com/datafeed/patchnotes?version=7.41b&language=english)).
- Другие источники Debuff Immunity: Elder Titan Astral Spirit (Scepter), Huskar Life Break, Juggernaut Blade Fury, Lifestealer Rage, Pangolier Rolling Thunder/Roll Up, Dawnbreaker Starbreaker (Shard), Chen Hand of God (Scepter), Lion Mana Drain (Shard), Omniknight Repel (с 7.41 даёт только Debuff Immunity и 60% магсопротивления) ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Пробивает Debuff Immunity** («pierces») — способность или дебафф действует полностью, включая урон, и игнорирует бонус магсопротивления от иммунитета; информация указана в тултипе каждой способности ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity); [оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english)).
- Предметы: **Abyssal Blade Overwhelm пробивает** иммунитет ([датафид-предмет Abyssal Blade](https://www.dota2.com/datafeed/itemdata?language=english&item_id=208)); **Shiva's Guard Freezing Aura пробивает** (с 7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)); Silver Edge Shadow Walk (Break, лимит скорости 200) **не пробивает** ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)). Ghost Scepter и Ethereal Blade не накладывают/не активны эфирную форму при Debuff Immunity (оф. 7.39e) ([оф. 7.39e](https://www.dota2.com/datafeed/patchnotes?version=7.39e&language=english)).
- По отношению к неуязвимости (7.40): большинство способностей и предметов больше **не могут** целиться/действовать на неуязвимые цели (в том числе в циклоне) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).

### Правила: Spell Immunity (старая терминология для нейтралов/неуязвимости)

- Блокирует большинство способностей: одноцелевые не могут целиться, AoE игнорируют юнит; некоторые способности (чаще ульты) пробивают иммунитет ([Liquipedia Spell Immunity](https://liquipedia.net/dota2/Spell_Immunity)).
- Не блокирует обычные атаки; пробивают иммунитет: критический удар, cleave, lifesteal, большинство bash ([Liquipedia Spell Immunity](https://liquipedia.net/dota2/Spell_Immunity)). Урон Battle Fury Cleave проходит сквозь иммунитет к заклинаниям ([датафид-предмет Battle Fury](https://www.dota2.com/datafeed/itemdata?language=english&item_id=145)).
- Сам иммунитет урон не снижает; если способность пробивает, её урон применяется как обычно любого типа ([Liquipedia Spell Immunity](https://liquipedia.net/dota2/Spell_Immunity)).

### Частые ошибки

- «BKB даёт спелл-иммунитет» — после 7.33 это Debuff Immunity; цель по-прежнему можно кастовать, дебаффы накладываются, но не действуют.
- «BKB снимает все дебаффы» — только базовый диспел при активации; потом дебаффы подавляются, а не снимаются; непроникающие дебаффы могут «сработать» после окончания Avatar.
- «BKB защищает от физического урона и атак» — нет.
- «BKB блокирует всё» — Abyssal Overwhelm, Shiva's Freezing Aura (с 7.41), Viper Strike, Nyx Vendetta (Shard) и многие ульты пробивают.
- «Отражённый урон Blade Mail бьёт героя в BKB» — не бьёт (с 7.41).
- «Дебафф исчез, раз BKB включился» — нет, он вернётся, если не истечёт раньше BKB.

### Что это значит для покупок

- BKB стоит брать против ультов без пробития и против жёсткого контроля; против героев с проникающим контролем (Abyssal, Bane Fiend's Grip, Beastmaster Primal Roar) защиты нет.
- Против BKB-кора нужны пробивающие источники: Abyssal Blade (актив), Shiva's Guard (аура пробивает с 7.41).
- Silver Edge (Break) бесполезен против героя в BKB (не пробивает).

---

## 6. Диспелы (Dispels)

### Правила

- Три уровня: **Basic Dispel** (базовый) < **Strong Dispel** (сильный) < **Death** (смерть) ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)).
- Basic снимает большинство статовых эффектов (замедления, бонусы к урону, молчание), но **не** снимает большинство жёстких контролей (станы, принудительное перемещение) ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)).
- Strong снимает все дебаффы, кроме тех, что снимаются только смертью ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)).
- На союзника диспел снимает только дебаффы; на врага — только баффы ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)).
- **Ауры не диспеллятся** (кроме смерти) ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)).
- **Предметы с базовым диспелом** ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116)): Black King Bar (на себя, [id 116](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116)); Manta Style (на себя, [id 147](https://www.dota2.com/datafeed/itemdata?language=english&item_id=147)); Lotus Orb Echo Shell ([id 226](https://www.dota2.com/datafeed/itemdata?language=english&item_id=226)); Satanic Unholy Rage ([id 156](https://www.dota2.com/datafeed/itemdata?language=english&item_id=156)); Nullifier Nullify (на врага, непрерывно диспеллит, [id 225](https://www.dota2.com/datafeed/itemdata?language=english&item_id=225)); Eul's Scepter / Wind Waker циклон ([id 100](https://www.dota2.com/datafeed/itemdata?language=english&item_id=100)); Disperser Suppress — диспеллит и владельца, и цель, с 7.40 диспел применяется к любой цели ([id 1097](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1097); [оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); Guardian Greaves Mend ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)); нейтральный Witchbane Cleanse (300 радиус, 7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Bloodstone Bloodpact больше не применяет базовый диспел** (7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Strong Dispel**: Aeon Disk Combo Breaker (пассивно при HP < 70%, +75% сопротивления статусу на 2.5 с, весь урон по вам и от вас нулевой; КД 105/125/145/165 с по уровням, старт 6 с) ([датафид-предмет Aeon Disk](https://www.dota2.com/datafeed/itemdata?language=english&item_id=256)); из способностей: Abaddon Aphotic Shield/Borrowed Time, Juggernaut Blade Fury, Oracle False Promise, Slark Dark Pact, Ursa Enrage, Weaver Time Lapse, Tidehunter Blubber, Roshan Roar of Retribution и др. ([Liquipedia Dispel](https://liquipedia.net/dota2/Dispel)).
- Ауры и некоторые перманентные эффекты не диспеллятся; но не диспеллятся и ряд дебаффов: **Khanda Break** ([датафид-предмет Khanda](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1808)); **Silver Edge** дебафф (лимит скорости 200) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); **Phantom Assassin Fan of Knives Break** (7.39c, [оф. 7.39c](https://www.dota2.com/datafeed/patchnotes?version=7.39c&language=english)); **Crimson Guard Guard** (7.40); **Heaven's Halberd Disarm** снимается только Strong Dispel (7.40) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); Roshan Roar of Retribution Disarm (7.40); Broodmother Spider's Milk (7.39).
- Hurricane Pike: бафф при цели-враге с 7.39c диспеллится ([оф. 7.39c](https://www.dota2.com/datafeed/patchnotes?version=7.39c&language=english)).
- Debuff Immunity не диспеллит дебаффы при получении; BKB делает это отдельно (базовый диспел) ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity); [датафид-предмет BKB](https://www.dota2.com/datafeed/itemdata?language=english&item_id=116)).
- Eul's/Wind Waker на себя проходит сквозь спелл-иммунитет; Eul's дроп урон 50 магического ([датафид-предмет Eul's](https://www.dota2.com/datafeed/itemdata?language=english&item_id=100)). Внимание: циклон делает цель неуязвимой, а после 7.40 большинство эффектов не могут таргетить неуязвимых (если циклон накладывают на цель, уже имеющую дебафф Nullify, циклон сразу снимается) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).

### Частые ошибки

- «Basic dispel снимает стан» — нет, большинство жёстких контролей он не снимает.
- «Диспел врага снимает его дебаффы» — вражеский диспел снимает только баффы врага.
- «Ауры (Shiva, Assault) можно развеять» — нет.
- «Bloodstone по-прежнему диспеллит» — с 7.41 нет.
- «Дебафф Heaven's Halberd снимается любым диспелом» — только сильным (с 7.40).
- «Aeon Disk даёт обычный диспел» — он даёт Strong Dispel.

### Что это значит для покупок

- Против обезоруживания Heaven's Halberd/Break-контроля Khanda/Silver Edge нужны Strong-диспелы (Aeon Disk) или иммунитет (BKB/Debuff Immunity у тех, что не пробивают).
- Nullifier снимает баффы (Ghost Scepter, Eul's, Glimmer и др.) и непрерывно диспеллит цель в течение 4 с.
- Lotus Orb и Manta — расходуемые «чистки» на себя; Satanic тоже чистит при активации.

---

## 7. Break (отключение пассивок)

### Правила

- Break отключает **пассивные способности героя/юнита** (в том числе шансы срабатывания, внутренние кулдауны, модификаторы атак, постоянные бонусы). **Не отключает** пассивные компоненты предметов и талантов (например evasion Talisman of Evasion и Butterfly, критический удар Daedalus) ([Liquipedia Break](https://liquipedia.net/dota2/Break)).
- Break не снимает уже наложенные баффы/дебаффы: Break лишь не даёт накладывать новые (например Poison Sting, уже висящий на цели, продолжает действовать); накопленные стаки (Essence Shift, Fury Swipes) обычно продолжают работать, новые не набираются ([Liquipedia Break](https://liquipedia.net/dota2/Break); [оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english) — «Breakability Update» с перечнем полностью/частично отключаемых).
- Если Break наложен на источник ауры, аура продолжает «существовать», но её эффект на других отключается; в HUD счётчик ауры показывает 0 ([Liquipedia Break](https://liquipedia.net/dota2/Break)).
- В 7.38 введена пометка «Breakable: Yes» в тултипах и список «полностью/частично отключаемых Break» способностей ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- **Источники Break** ([Liquipedia Break](https://liquipedia.net/dota2/Break); значения предметов — [датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=249)):
  - Предметы: **Silver Edge** Shadow Walk (при атаке из невидимости ломает пассивки на 5 с и ограничивает скорость цели до 200; не пробивает Debuff Immunity, не диспеллится) ([id 249](https://www.dota2.com/datafeed/itemdata?language=english&item_id=249); [оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); **Khanda** Empower Spell (следующее таргетное заклинание на врага; Break не диспеллится, замедление диспеллится) ([id 1808](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1808); [оф. 7.39c](https://www.dota2.com/datafeed/patchnotes?version=7.39c&language=english)).
  - Способности: Doom Doom (талант), Hoodwink Decoy/Sharpshooter, Naga Siren Ensnare (Scepter, с 7.39), Nyx Vendetta (Shard), Phantom Assassin Fan of Knives (Scepter; Break 4 с с 7.39), Primal Beast Uproar (Scepter), Shadow Demon Demonic Purge (Scepter), Shadow Shaman Hex (талант), Viper Viper Strike ([Liquipedia Break](https://liquipedia.net/dota2/Break); [оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)).
  - Пробивают Debuff Immunity (по Liquipedia): Viper Strike, Nyx Vendetta, PA Fan of Knives, Shadow Demon Demonic Purge (при соответствующих улучшениях) ([Liquipedia Break](https://liquipedia.net/dota2/Break)) `(не проверено для 7.41f)`.
- Debuff Immunity блокирует Break от источников, которые её не пробивают ([Liquipedia Debuff Immunity](https://liquipedia.net/dota2/Debuff_Immunity)).
- «Break» у **Tranquil Boots** — это другая механика (при атаке героя или получении удара теряется бонус регенерации, скорость падает до 40 на 13 с), не статус Break ([датафид-предмет Tranquil Boots](https://www.dota2.com/datafeed/itemdata?language=english&item_id=214)).

### Частые ошибки

- «Break отключает предметные пассивки (MKB, Butterfly, Daedalus)» — нет, только способности героя.
- «Break снимает уже накопленные стаки» — обычно нет; он блокирует набор новых.
- «Break и Silence — одно и то же» — разные эффекты: Silence блокирует активные способности, Break — пассивные.
- «Tranquil Boots "Break" — это статус Break» — нет, это отдельная внутренняя механика.

### Что это значит для покупок

- Против героев, чья сила в пассивках (Phantom Assassin, Spectre, Troll, Ursa, Slark, Bristleback), Silver Edge/Khanda — сильные ответы; но против носителя BKB Silver Edge не пробьёт.
- Break не ломает предметные пассивки, поэтому «сломанный» кор с Butterfly/Daedalus всё равно уклоняется/критует.

---

## 8. Уклонение (Evasion), True Strike, Accuracy

### Правила

- Evasion даёт шанс уклониться от атаки; проверяется при попадании (для дальних — при ударе снаряда, для ближних — в момент атаки) ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)).
- Все источники evasion **стакаются убывающе (мультипликативно)**: итого = 1 − Π(1 − evasion_i); у Talisman of Evasion и Butterfly прямо: «Stacks diminishingly with other sources of Evasion» ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion); [датафид-предмет Butterfly](https://www.dota2.com/datafeed/itemdata?language=english&item_id=139)). Пример: Butterfly 35% + Radiance 25% + Heaven's Halberd 25% → 1 − 0.65×0.75×0.75 = **63.4%** (расчёт).
- Evasion даётся с псевдослучайным распределением (PRD), если значение не 0 и не 100% ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)).
- Предметы (датафид): **Butterfly 35%** ([id 139](https://www.dota2.com/datafeed/itemdata?language=english&item_id=139)); **Radiance 25%** (7.40: 15→25) ([id 137](https://www.dota2.com/datafeed/itemdata?language=english&item_id=137); [оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); **Heaven's Halberd 25%** (с 7.41 даёт также +9 брони) ([id 210](https://www.dota2.com/datafeed/itemdata?language=english&item_id=210); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)); **Talisman of Evasion 15%** (7.39: 20→15) ([id 32](https://www.dota2.com/datafeed/itemdata?language=english&item_id=32)). Нейтральный (Tier 3) Idol of Scree'auk — актив False Flight: 35% evasion, 50% сопротивления замедлениям, фазовое движение, 6.5 с ([датафид-предмет](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1720); [оф. 7.41d](https://www.dota2.com/datafeed/patchnotes?version=7.41d&language=english)); Sister's Shroud — до 150% evasion при HP < 50% (оф. 7.39d) ([оф. 7.39d](https://www.dota2.com/datafeed/patchnotes?version=7.39d&language=english)).
- **Слепота (blind)** суммируется аддитивно до 100% и затем умножается с evasion цели ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)).
- **Промах вверх по склону (uphill miss)**: дальние атаки юнитов без полёта имеют 25% шанс промаха, если атакующий на более низкой высоте; считается источником evasion ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)). С 7.41 юниты со свободным перемещением (Batrider Firefly, Dragon Knight Elder Dragon Form со Scepter, Lina Flame Cloak, иллюзии Terrorblade Reflection) тоже могут промахиваться по цели на возвышении ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Ближние юниты**: если цель дальше дальности атаки + буфера 350, атака промахивается на 100% и True Strike это не исправляет ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)).
- **True Strike** — атака не может промахнуться (игнорирует evasion и слепоту, но не отменяет промах ближней атаки за буфером и не отменяет перехват снаряда); не работает по зданиям ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)). Все атаки по рунам и разрушаемым предметам имеют True Strike.
- **Accuracy (точность)** — дебафф на цели: входящие атаки не могут промахнуться; 100% accuracy исключает все промахи; значения меньше 100% — шансовый True Strike. Формула: итоговый шанс попасть = 1 − (эффективное уклонение) × (1 − суммарная точность) ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)).
- **Источники True Strike/Accuracy** (текущие значения — [датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=135)): **Monkey King Bar** Pierce — 80% шанс пробить evasion, +70 магического урона ([id 135](https://www.dota2.com/datafeed/itemdata?language=english&item_id=135)); **Bloodthorn** — актив Soul Rend (цель на 5 с получает «Provides True Strike for your attacks and attacks from your controlled units against the silenced target»; в текущем описании предмета критического удара нет) и пассивный Pierce 40% с +60 магического урона ([id 250](https://www.dota2.com/datafeed/itemdata?language=english&item_id=250)); **Javelin** Pierce — шанс 25%, +60 магического урона ([id 7](https://www.dota2.com/datafeed/itemdata?language=english&item_id=7)); **Maelstrom** и **Mjollnir** Chain Lightning — шанс 25%, «Lightning proc pierces evasion» ([Maelstrom id 166](https://www.dota2.com/datafeed/itemdata?language=english&item_id=166), [Mjollnir id 158](https://www.dota2.com/datafeed/itemdata?language=english&item_id=158)); Parasma/Witch Blade, Silver Edge Shadow Walk — гарантированный True Strike ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion)) `(не проверено для 7.41f)`.
- Официальные изменения последних патчей: Orb of Venom больше не имеет True Strike на атаке (7.39c); Kez Shodo Sai Mark больше не даёт True Strike (7.39); Serrated Shiv Gut'Em больше не даёт иллюзиям шанс True Strike (7.39c) ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english), [оф. 7.39c](https://www.dota2.com/datafeed/patchnotes?version=7.39c&language=english)).
- Evasion и True Strike работают только на **атаки**; уклониться от заклинаний evasion нельзя ([Liquipedia Evasion](https://liquipedia.net/dota2/Evasion): «Spell damage-based attacks ignore evasion and blind»).

### Частые ошибки

- «Evasion складывается» — нет, убывающе (35%+25% ≠ 60%, а 51.25%).
- «MKB даёт True Strike всегда» — только 80% атак (PRD).
- «Bloodthorn даёт крит» — в текущей версии предмета критического удара нет; он даёт Soul Rend (True Strike по цели) и Pierce 40%.
- «True Strike заставляет ближнюю атаку достать убежавшую цель» — нет, буфер 350 всё равно действует.
- «Evasion защищает от способностей» — нет, только от атак.
- «Evasion от Butterfly отключается Break» — нет, предметные пассивки не ломаются.

### Что это значит для покупок

- Против evasion-героев: MKB (80% Pierce, +50 AS) или Bloodthorn (Soul Rend даёт True Strike по цели на 5 с и по атакам ваших юнитов); Javelin (25% Pierce) даёт лишь часть пробивающих атак.
- Не стоит ставить третий-четвёртый источник evasion на кора: убывающая отдача; Radiance и Heaven's Halberd дают по 25% и стакаются убывающе.
- Heaven's Halberd с 7.41 даёт броню +9 и evasion 25% — полезнее против физ-кора, чем Butterfly по соотношению цены.

---

## 9. Статус-сопротивление (Status Resistance) и сопротивление замедлениям (Slow Resistance)

### Правила — Status Resistance

- Статус-сопротивление **сокращает длительность** большинства дебаффов; базово у всех юнитов 0 ([Liquipedia Status Resistance](https://liquipedia.net/dota2/Status_Resistance)).
- Источники стакаются **мультипликативно**: итог = 1 − Π(1 − SR_i); сто процентов набрать нельзя ([Liquipedia Status Resistance](https://liquipedia.net/dota2/Status_Resistance)). Пример Liquipedia: Bulldoze 50% + Sange and Yasha 16% → 58% ([там же](https://liquipedia.net/dota2/Status_Resistance)).
- Предметы-источники сегодня: **Sange and Yasha 16%** (7.41: +16%) ([датафид-предмет](https://www.dota2.com/datafeed/itemdata?language=english&item_id=154)); **Aeon Disk** Combo Breaker +75% на 2.5 с ([id 256](https://www.dota2.com/datafeed/itemdata?language=english&item_id=256)); Trident 30% ([id 369](https://www.dota2.com/datafeed/itemdata?language=english&item_id=369)) `(не проверено для 7.41f)` — в датафиде у Trident нет описания и рецепта; нейтральное Titanic Enchantment +10/12/14% (7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- Статус-сопротивление от разных Sange-based предметов (Sange and Yasha и др.) **не стакается между собой** — берётся максимум ([Liquipedia Status Resistance](https://liquipedia.net/dota2/Status_Resistance)).
- С 7.34 статус-сопротивление **не влияет на силу замедления**, только на его длительность; силу замедления уменьшает Slow Resistance ([оф. 7.34](https://www.dota2.com/datafeed/patchnotes?version=7.34&language=english)).
- Не уменьшается: аура-эффекты, постоянные модификаторы, урон-во-времени (суммарный урон не меняется, тики подстраиваются), эффекты-задержки; новое значение действует только на дебаффы, наложенные после изменения ([Liquipedia Status Resistance](https://liquipedia.net/dota2/Status_Resistance)).
- Длительность циклона от статус-сопротивления не зависит ([датафид-предмет Eul's](https://www.dota2.com/datafeed/itemdata?language=english&item_id=100)).
- Tormentor имеет 25% статус-сопротивления (7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).

### Правила — Slow Resistance

- Slow Resistance уменьшает силу замедления **движения**; введена в 7.34 ([оф. 7.34](https://www.dota2.com/datafeed/patchnotes?version=7.34&language=english)). Применяется к процентной величине замедления: итог = замедление × Π(1 − SR_i) ([Liquipedia Slow Resistance](https://liquipedia.net/dota2/Slow_Resistance)).
- Источники Slow Resistance стакаются мультипликативно; пример Liquipedia: замедление 25% при 40% и 25% сопротивления → 25% × (1−0.55) = 11.25% ([Liquipedia Slow Resistance](https://liquipedia.net/dota2/Slow_Resistance)).
- С 7.38 Slow Resistance также **повышает минимальную скорость** на свой процент: 20% SR поднимает минимум со 100 до 120 ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- Предметы (датафид, 7.41f): **Sange 25%**, **Kaya and Sange 25%**, **Sange and Yasha 30%**, **Abyssal Blade 30%**, **Disperser Suppress 40%** (временно, союзнику/на себя), **Mask of Madness Berserk 15% / 30%** (дальний/ближний, с 7.41e) ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=162): [Sange 162](https://www.dota2.com/datafeed/itemdata?language=english&item_id=162), [Kaya and Sange 273](https://www.dota2.com/datafeed/itemdata?language=english&item_id=273), [S&Y 154](https://www.dota2.com/datafeed/itemdata?language=english&item_id=154), [Abyssal 208](https://www.dota2.com/datafeed/itemdata?language=english&item_id=208), [Disperser 1097](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1097), [MoM 172](https://www.dota2.com/datafeed/itemdata?language=english&item_id=172); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english), [оф. 7.41e](https://www.dota2.com/datafeed/patchnotes?version=7.41e&language=english)). Нейтральные: Unrelenting Eye до 50% (−10% за каждого вражеского героя в радиусе атаки) ([датафид-предмет](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1598); [оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)); Brawny Enchantment +25% на Tier 4 (7.39) ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)).
- Стакается ли Slow Resistance от нескольких Sange-based предметов между собой — в источниках явно не указано `(не проверено для 7.41f)`.
- Roshan имеет 25% базового Slow Resistance (плюс 25% при беге между ямами) ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).

### Частые ошибки

- «Status Resistance уменьшает замедления» — с 7.34 уменьшает только их длительность; силу уменьшает Slow Resistance.
- «Статус-сопротивление можно довести до 100%» — нет, мультипликативно.
- «Sange и Sange and Yasha дают суммарно 36% статус-сопротивления» — у Sange нет статус-сопротивления (только Slow Resistance и Health Restoration), а Sange-based SR не стакается.
- «Slow Resistance укорачивает замедление» — не длительность, а силу.
- «Статус-сопротивление сокращает урон DOT» — суммарный урон не меняется, только тики адаптируются.

### Что это значит для покупок

- Sange-предметы дают сопротивление замедлениям и усиление лечения — вторая покупка Sange-based предмета ради SR/HR бесполезна.
- Против «замедляющих» команд (Shiva, Skadi, Orb) полезны Sange/Abyssal/Disperser (Slow Resistance), против станов — статус-сопротивление (S&Y, Aeon Disk).
- Aeon Disk одновременно Strong Dispel + 75% SR на 2.5 с + нулевой урон — подходит против burst.

---

## 10. Lifesteal, Spell Lifesteal, Health Restoration, снижение лечения

### Терминология

- С 7.39 термины «Lifesteal Amplification» и «Spell Lifesteal Amplification» **удалены**; на их месте единая характеристика **Health Restoration** — процентное изменение здоровья от Lifesteal, Spell Lifesteal и регенерации; при отрицательном значении снижает их ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)).
- **С 7.41 Health Restoration применяется ко всем видам получения HP**, включая входящие хилы («Previously, it did not apply to incoming heals») ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- Heal Amplification (усиление хилов): с 7.39 источники **суммируются аддитивно** (раньше убывающе), нижний предел −100%, верхнего нет ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)).
- 7.41: «Incoming Heal Amplification now stacks diminishingly with Health Restoration instead of additively with Outgoing Heal Amplification» — то есть входящее усиление хилов теперь объединяется с Health Restoration убывающе, а исходящее (Holy Locket Holy Blessing) — отдельная группа ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)). Точная итоговая формула для 7.41f в заметках не опубликована `(не проверено для 7.41f)`; формула 7.39 для самой Health Restoration (ниже) остаётся в силе.

### Правила — Health Restoration

- Положительные источники Health Restoration стакаются убывающе: итог = 1 − (1−n0)(1−n1)…; отрицательные — так же; затем положительное и отрицательное значения складываются; диапазон **−100% … +100%** ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english): пример Sange 16% + Crude 20% = 32.8%; [Liquipedia Restoration manipulation](https://liquipedia.net/dota2/Health_Restoration)).
- Пример расчёта (по этой формуле): Eye of Skadi (−50%) и Spirit Vessel (−70%) → отрицательная часть = 1−0.5×0.3 = **85%** снижения.
- **Источники сокращения лечения (7.41f, датафид-предметы)**: **Spirit Vessel** Soul Release на враге −70% ([id 267](https://www.dota2.com/datafeed/itemdata?language=english&item_id=267)); **Eye of Skadi** Cold Attack −50% (7.41: 40→50) ([id 160](https://www.dota2.com/datafeed/itemdata?language=english&item_id=160)); **Orb of Corrosion** −18% (7.41e: 16→18) ([id 569](https://www.dota2.com/datafeed/itemdata?language=english&item_id=569)); **Orb of Frost** −15% (7.41e: 13→15) ([id 1575](https://www.dota2.com/datafeed/itemdata?language=english&item_id=1575)); нейтральные: **Jidi Pollen Bag** −50% (7.41), **Crippling Crossbow** −40% (52% с Curio) (оф. 7.39), Crella's Crozier Putrefaction Aura −30% (−75% при активном Rite of Rumusque) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english), [оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)). Из героев: Abaddon Withering Mist, Slark Saltwater Shiv, Drow Ranger Frost Arrows (Scepter), Pudge Rot (Scepter), Omniknight Guardian Angel (Scepter) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Shiva's Guard больше не снижает Health Restoration** (7.41: «Freezing Aura no longer reduces Health Restoration and Incoming Heal Amplification by 25%»; аура теперь только −40 к скорости атаки, пробивает Debuff Immunity) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english); [датафид-предмет](https://www.dota2.com/datafeed/itemdata?language=english&item_id=119)). Устаревшее представление «Shiva режет лечение на 25%» неверно для 7.41f.
- Orb of Frost, Orb of Corrosion и Eye of Skadi: **замедление и снижение Health Restoration не стакаются между собой** (7.39) ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)); отмены в заметках 7.40–7.41f не найдено.
- **Источники повышения Health Restoration**: Sange **+12%** (7.41b: 16→12), Abyssal Blade **+16%**, Sange and Yasha **+16%**, Kaya and Sange **+16%** (7.41b: 20→16) ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=162); [оф. 7.41b](https://www.dota2.com/datafeed/patchnotes?version=7.41b&language=english)); нейтральная Crude Enchantment +9/12/15% (7.41b) ([оф. 7.41b](https://www.dota2.com/datafeed/patchnotes?version=7.41b&language=english)); Legion Commander Outfight Them! +30/40/50/60% (7.39) ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)). Sange-based бонусы не стакаются между собой, берётся максимум ([Liquipedia Restoration manipulation](https://liquipedia.net/dota2/Health_Restoration)).
- С 7.41 способности, у которых раньше было отдельное значение «снижения входящих хилов» (Eye of Skadi, Spirit Vessel, Omniknight Guardian Angel со Scepter, Pudge Rot со Scepter), теперь изменяют только Health Restoration; а Sange, Kaya and Sange, Sange and Yasha, Abyssal Blade, Orb of Frost/Corrosion, Crippling Crossbow, Jidi, Crude, Withering Mist, Frost Arrows (Scepter), Saltwater Shiv дополнительно затрагивают входящие хилы ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Health Freeze** (Ancient Apparition Ice Blast, Doom, Oracle False Promise) полностью блокирует лечение: значения регистрируются, но здоровье не растёт ([Liquipedia Restoration manipulation](https://liquipedia.net/dota2/Health_Restoration)).

### Правила — Lifesteal (атаки)

- Lifesteal лечит от **физического** урона атаки (процент от нанесённого урона); работает с критами; единый набор правил с 7.38 ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- Против **негероев** Lifesteal уменьшен на **40%**; Spell Lifesteal против негероев — на **80%** (7.38) ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)). Roshan с 7.40 не считается героем для lifesteal (физ. −40%, спелл −80%) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).
- Ни Lifesteal, ни Spell Lifesteal **не применяются к чистому урону** (7.38) ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- Нет lifesteal: от атак, не вызывающих модификаторы атаки (Cleave, Luna Moon Glaives), от атак по вардам/зданиям/курьерам, от spell-урона по иллюзиям/вардам/зданиям/курьерам, от отражённого урона, от способностей, снимающих HP (Orb of Venom, Heartstopper Aura), от урона по себе или союзникам ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- **С 7.41 физический и магический lifesteal учитывают общие снижения/усиления урона** при расчёте: нельзя лечиться от атаки, нанёсшей 0 урона (пример: Aeon Disk Combo Breaker); единственное неучитываемое усиление — повышенный урон против иллюзий ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- Предметы Lifesteal (датафид): **Satanic 25%** (7.41f: 30→25; актив +145% на 6 с, итого 175%), **Mask of Madness 22%** (7.41f: 24→22), **Morbid Mask 18%**, Vladmir's Offering аура 20% ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=156): [Satanic 156](https://www.dota2.com/datafeed/itemdata?language=english&item_id=156), [MoM 172](https://www.dota2.com/datafeed/itemdata?language=english&item_id=172); [оф. 7.41f](https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english)). Вампирский нейтрал Vampiric Enchantment 30% lifesteal / 20% spell lifesteal (7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- Lifesteal источников складывается аддитивно, затем применяется Health Restoration ([Liquipedia Lifesteal](https://liquipedia.net/dota2/Lifesteal)) `(не проверено для 7.41f)` в части порядка.

### Правила — Spell Lifesteal

- Лечит от spell-урона (физ. и маг. спелл-урон; после всех снижений); **не лечит от перебора урона** (считается от оставшегося у цели HP) ([Liquipedia Spell Lifesteal](https://liquipedia.net/dota2/Spell_Lifesteal); [оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english): «Spell Lifesteal now applies to physical damage from spells and magical damage from spells or attacks»).
- Источники (датафид): **Bloodstone 20%** (7.41: 25→20; Bloodpact: 60% на 5 с вместо ×3), **Veil of Discord 18%** (7.41: новый), **Voodoo Mask 15%**, **Revenant's Brooch 15%** ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=121): [Bloodstone 121](https://www.dota2.com/datafeed/itemdata?language=english&item_id=121); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)). Kaya, Yasha and Kaya, Meteor Hammer больше не дают Spell Lifesteal Amplification (7.39) ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)). Dagon больше не даёт spell lifesteal (7.41).
- Несколько одинаковых источников (две Bloodstone) не стакаются, разные источники суммируются ([Liquipedia Spell Lifesteal](https://liquipedia.net/dota2/Spell_Lifesteal)).

### Частые ошибки

- «Есть Lifesteal Amplification / Spell Lifesteal Amplification» — удалены, теперь Health Restoration (7.39).
- «Health Restoration не влияет на хилы» — с 7.41 влияет.
- «Shiva's Guard режет лечение» — не режет с 7.41.
- «Reductions складываются: Skadi 50% + Vessel 70% = 120%» — убывающе: 85%; предел −100%.
- «Skadi + Orb of Corrosion + Orb of Frost: три замедления/три снижения лечения» — не стакаются между собой (7.39).
- «Satanic лечит 30%/Mask 24%» — после 7.41f 25% и 22%.
- «Lifesteal лечит от чистого/отражённого урона» — нет.
- «Roshan — герой для lifesteal» — нет с 7.40.
- «Lifesteal лечит при Aeon Disk Combo Breaker» — не лечит с 7.41.

### Что это значит для покупок

- Spirit Vessel (−70%) + Skadi (−50%) вместе дают −85% (один Vessel — уже −70%): второй источник добавляет всего 15 п.п. из-за убывающего стакания.
- Не нужно ставить Shiva ради «анти-хила»: с 7.41 это не работает; Shiva даёт броню и −40 AS (аура пробивает BKB).
- Против Aeon Disk/нулевого урона бессмысленно рассчитывать на lifesteal-ответ.
- Sange-предметы дают +12–16% Health Restoration — второй такой предмет не стакается.

---

## 11. Скорость атаки, BAT, модификаторы атаки, криты, баши, клив

### Правила — скорость атаки и BAT

- Скорость атаки (AS) = (базовая AS 100 + бонус от Agi + плоские бонусы) × (1 + процентные); атак в секунду = AS / (100 × BAT); интервал между атаками T = BAT × 100 / AS ([Liquipedia Attack Speed](https://liquipedia.net/dota2/Attack_Speed)).
- Пределы: по Liquipedia минимум **20**, максимум **700** (некоторые способности вроде Marci Unleash и Troll Battle Trance поднимают максимум) ([Liquipedia Attack Speed](https://liquipedia.net/dota2/Attack_Speed)) `(не проверено для 7.41f)` в части максимума: в 7.38 отображение AS перестало нормироваться к 1.7 BAT — «heroes' max attack speed is no longer always 700»; игровой эффект «No actual gameplay change» ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)). Страница Liquipedia этого изменения не отражает.
- Примеры: BAT 1.7, AS 100 → 0.588 атак/с; AS 200 → 1.176 атак/с (расчёт по формуле). BAT 1.4 (Juggernaut, Anti-Mage) делает ту же AS быстрее: AS 100 → 0.714 атак/с.
- Снижающие BAT источники стакаются с установкой BAT; установка BAT: первая полученная способность имеет приоритет (исключения — Terrorblade Metamorphosis, Kez Switch Discipline) ([Liquipedia Attack Speed](https://liquipedia.net/dota2/Attack_Speed)) `(не проверено для 7.41f)`. Нейтральный Crude Enchantment в 7.41 снижает BAT на 8/12/16%, затем в 7.41a на 6/9/12% (и штрафует Intelligence: 9% с 7.41c) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english), [оф. 7.41a](https://www.dota2.com/datafeed/patchnotes?version=7.41a&language=english), [оф. 7.41c](https://www.dota2.com/datafeed/patchnotes?version=7.41c&language=english)).
- Замедления скорости атаки (Skadi, Shiva) работают отдельно; Shiva's Freezing Aura: −40 к AS в радиусе 1200 (7.41c: 45→40), несколько Shiva не стакаются ([датафид-предмет Shiva's Guard](https://www.dota2.com/datafeed/itemdata?language=english&item_id=119); [оф. 7.41c](https://www.dota2.com/datafeed/patchnotes?version=7.41c&language=english)). Skadi: −25 AS (7.41e: 20→25) ([датафид-предмет Skadi](https://www.dota2.com/datafeed/itemdata?language=english&item_id=160)).

### Правила — модификаторы атаки

- «Unique Attack Modifiers» (UAM, они же «orb effects») — **исторический термин**: Liquipedia пишет в прошедшем времени, что такие эффекты не стакались и один перекрывал другой; в 7.06–7.07 Frost Arrows, Caustic Finale, Corruption, Mana Break, Arcane Orb, Morbid Mask, Mask of Madness, Satanic перестали быть UAM ([Liquipedia Attack Modifier](https://liquipedia.net/dota2/Attack_Modifier)). В текущих описаниях предметов нет упоминаний «unique attack modifier»; вместо этого у конкретных предметов явные правила нестакания (ниже) ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=569)).
- Явные правила нестакания в 7.41f: **Skull Basher/Abyssal Blade** — не стакается с другими источниками Bash; **Diffusal Blade** — не стакается с другими Diffusal ([датафид-предмет Diffusal](https://www.dota2.com/datafeed/itemdata?language=english&item_id=174)); **Orb of Venom** — не стакается с апгрейдами; **Orb of Blight/Corrosion** — снижение брони не стакается с компонентами, Desolator и Stygian Desolator ([датафид-предмет Orb of Corrosion](https://www.dota2.com/datafeed/itemdata?language=english&item_id=569)).
- Mana Break (Anti-Mage) стакается с Manabreak (Diffusal/Disperser) с 7.31 ([Liquipedia Attack Modifier](https://liquipedia.net/dota2/Attack_Modifier)). Мана-ломка не применяется иллюзиями (7.40) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).
- Модификаторы атаки вычисляются в начале атаки и не применяются при промахе; on-hit эффекты — при попадании ([Liquipedia Attack Modifier](https://liquipedia.net/dota2/Attack_Modifier)).
- Если способность стреляет несколькими снарядами (Drow Marksmanship, Split Shot), все модификаторы на основной цели; побочные цели получают не все ([Liquipedia Attack Modifier](https://liquipedia.net/dota2/Attack_Modifier)). С 7.41 у Dragon Knight Elder Dragon Form «other attack modifiers will affect only the primary target» ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).

### Правила — критический удар (crit)

- Несколько источников крита **не стакаются**: бросаются от сильнейшего множителя к слабейшему, как только один сработал, остальные не бросаются; действует только наибольший множитель ([Liquipedia Critical Strike](https://liquipedia.net/dota2/Critical_Strike); введено в 7.30).
- Шанс критов псевдослучайный (PRD); крит определяется в начале атаки; множитель применяется до снижений урона (броня и т. д.) ([Liquipedia Critical Strike](https://liquipedia.net/dota2/Critical_Strike)).
- Крит умножает основной урон и бонусный урон атаки (плоский и процентный), но не отдельные «инстансы» условного урона (Bash, Mana Break, Drow Frost Arrows, Spectre Desolate, Ursa Fury Swipes, Pierce MKB и др.) ([Liquipedia Critical Strike](https://liquipedia.net/dota2/Critical_Strike)).
- Крит с lifesteal и cleave: lifesteal и cleave учитывают увеличенный крит-урон ([Liquipedia Critical Strike](https://liquipedia.net/dota2/Critical_Strike)).
- Предметы (датафид): **Daedalus** 30% на 225% (+88 урона; цена 5200 после 7.41f) ([id 141](https://www.dota2.com/datafeed/itemdata?language=english&item_id=141); [оф. 7.41f](https://www.dota2.com/datafeed/patchnotes?version=7.41f&language=english)); **Crystalys** 30% на 160% ([id 149](https://www.dota2.com/datafeed/itemdata?language=english&item_id=149)); критический удар не работает по зданиям. Нейтральный Giant's Maul Crushing Blow: следующая атака крит 140% (7.40) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).
- Bloodthorn в текущем описании крита **не имеет** ([датафид-предмет Bloodthorn](https://www.dota2.com/datafeed/itemdata?language=english&item_id=250)).

### Правила — Bash (оглушение атакой)

- Несколько источников Bash **не стакаются**: срабатывает только тот, что дольше всего непрерывно находится в инвентаре ([Liquipedia Bash](https://liquipedia.net/dota2/Bash); [датафид-предмет Skull Basher](https://www.dota2.com/datafeed/itemdata?language=english&item_id=143): «Does not stack with other sources of Bash»).
- **Ближний/дальний бой**: Skull Basher и Abyssal Blade — шанс **25% у ближних** героев и **10% у дальних**; оглушение 1.2 с, КД 2.3 с; бонусный физический урон Basher 100, Abyssal 120 ([датафид-предмет Skull Basher](https://www.dota2.com/datafeed/itemdata?language=english&item_id=143); [датафид-предмет Abyssal](https://www.dota2.com/datafeed/itemdata?language=english&item_id=208)).
- Герои, которые **не могут** проковать Bash с предметов: Spirit Breaker, Faceless Void, Slardar, Kez (в режиме Sai); Bash не выдаётся клонам и Tempest Double ([датафид-предмет Skull Basher](https://www.dota2.com/datafeed/itemdata?language=english&item_id=143)); иллюзии тоже ([Liquipedia Bash](https://liquipedia.net/dota2/Bash)).
- Bash не действует на здания и варды; бонусный урон Bash добавляется к атаке, поэтому не крит-ится и не клив-ится ([Liquipedia Bash](https://liquipedia.net/dota2/Bash), [Liquipedia Attack Modifier](https://liquipedia.net/dota2/Attack_Modifier)).
- Abyssal Blade Overwhelm — актив, стан 1.6 с, **пробивает Debuff Immunity** ([датафид-предмет Abyssal](https://www.dota2.com/datafeed/itemdata?language=english&item_id=208)).
- Bash проходит сквозь спелл-иммунитет в большинстве случаев (но по отдельным модификаторам есть исключения) ([Liquipedia Spell Immunity](https://liquipedia.net/dota2/Spell_Immunity)).

### Правила — Cleave (клив)

- Cleave — только **ближние** юниты (дальние не клив-ят, кроме особого случая Ability Draft) ([Liquipedia Cleave](https://liquipedia.net/dota2/Cleave); [датафид-предмет Battle Fury](https://www.dota2.com/datafeed/itemdata?language=english&item_id=145): «(Melee Only)»).
- Урон кливa — **физический** и зависит от суммарного урона атаки до снижений; **снижается бронёй каждой цели** (с 7.20) ([Liquipedia Cleave](https://liquipedia.net/dota2/Cleave)).
- Область — равнобедренная трапеция перед атакующим; Battle Fury: ширина старта 150, конца 360, дальность 650; **60% урона** по героям, **40% по крипам** ([датафид-предмет Battle Fury](https://www.dota2.com/datafeed/itemdata?language=english&item_id=145)).
- Cleave не бьёт основную цель, не промахивается по вторичным целям; промахнувшаяся атака не клив-ит; не работает по вардам и зданиям; проходит сквозь спелл-иммунитет ([Liquipedia Cleave](https://liquipedia.net/dota2/Cleave); [датафид-предмет Battle Fury](https://www.dota2.com/datafeed/itemdata?language=english&item_id=145): «Cleave damage goes through spell immunity»).
- Несколько источников кливa **работают независимо**: у каждого свой урон и область ([Liquipedia Cleave](https://liquipedia.net/dota2/Cleave); [датафид-предмет Battle Fury](https://www.dota2.com/datafeed/itemdata?language=english&item_id=145): «each Cleave's damage is applied separately»).
- У кливa флаги No-spell-amplification и No-spell-lifesteal: spell amp его не усиливает, spell lifesteal не лечит; lifesteal от самой атаки не распространяется на клив (7.38: атаки, не вызывающие модификаторы атаки, lifesteal не дают) ([Liquipedia Cleave](https://liquipedia.net/dota2/Cleave); [оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- Cleave и модификаторы увеличения урона атаки (крит) работают вместе: крит увеличивает клив-урон; снижение брони от Corruption на основной цели клив-урон по другим не увеличивает ([Liquipedia Cleave](https://liquipedia.net/dota2/Cleave)).
- С 7.38 бонусы к области (AoE) действуют и на ауры, и на источники кливa (AoE Bonuses now affect all auras and Cleave sources) ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).

### Частые ошибки

- «BAT — лишь визуальный параметр» — это базовый интервал между атаками; скорость атаки без BAT не даёт атак/с.
- «У всех героев макс. AS 700 в одних единицах» — после 7.38 отображение не нормировано (но геймплейно ничего не менялось); не путать отображаемое число с реальным.
- «Два крита складываются / два шанса суммируются» — нет, действует один (наибольший множитель).
- «Skull Basher шанс 25% у всех» — 25% у ближних, 10% у дальних.
- «Два Skull Basher увеличивают шанс» — не стакаются.
- «Клив работает у дальних героев (Medusa/Drow/Sniper)» — нет (кроме Ability Draft).
- «Cleave игнорирует броню» — нет, с 7.20 учитывается броня.
- «Bloodthorn крит» — нет в текущем описании.
- «Orb Effects/UAM — действующее правило» — исторически; в 7.41f работают конкретные предметные оговорки.

### Что это значит для покупок

- Не покупать второй крит-предмет (Daedalus + Crystalys): сработает только больший множитель; есть смысл только ради статов/AS.
- Не покупать второй Bash-предмет; для дальних героев Basher/Abyssal слабы (10%).
- Battle Fury — только для ближнего кора против групп крипов/героев (60/40%).
- При покупке AS-предметов учитывать BAT героя: у BAT 1.4 тот же AS даёт больше атак/с.

---

## 12. Скорость передвижения (Movement Speed)

### Правила

- Формула: **скорость = (база + плоские бонусы) × (1 + сумма процентных бонусов/замедлений)**; затем применяются пределы ([Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed)).
- Пределы по умолчанию: **минимум 100, максимум 550** — применяются после расчёта; пример Liquipedia: расчётные 773.5 → 550 ([Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed)).
- Способы превысить 550: Windranger Tailwind (пассивно: макс. скорость 600, 7.41) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)); Bloodseeker Thirst; Spirit Breaker Charge of Darkness; Broodmother Spin Web (талант); бывший нейтральный предмет Force Boots «Speed Unlock» (убирал лимит скорости; в списке нейтральных предметов 7.41f его нет, не проверено для 7.41f) ([Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed); [датафид-предмет Force Boots](https://www.dota2.com/datafeed/itemdata?language=english&item_id=291); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
- **Haste (ускорение)**: фиксирует и минимум, и максимум на значении haste; цель нельзя замедлить ниже него. Haste Rune — скорость **550**, длительность **22 с** (7.40: больше не растёт с циклами рун) ([Liquipedia Runes](https://liquipedia.net/dota2/Runes), [Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed); [оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).
- **Бонус скорости ночью убран** в 7.38 ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- **Течения рек (7.41)**: любой участок течения даёт до +150 к максимальной скорости (раньше 100 на «умеренных» участках) ([оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)); бонус зависит от направления: 100% по течению, 0% под 90° ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- **Плоские бонусы** от ботинок одной группы **не стакаются** (берётся максимум): «Movement speed bonuses from multiple pairs of boots do not stack» ([датафид-предмет Boots of Speed](https://www.dota2.com/datafeed/itemdata?language=english&item_id=29)). Значения: Boots of Speed +45, Phase Boots +50, Tranquil Boots +65 (при ударе 40 на 13 с), Boots of Bearing +65, Boots of Travel +90, Boots of Travel 2 +110 ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=29)).
- **Процентные бонусы**: Yasha-группа (Yasha, Sange and Yasha, Yasha and Kaya, Manta) **не стакается между собой**: S&Y +12%, Manta +10% ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=154): «Yasha-based movement speed bonuses from multiple items do not stack»; [Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed)). Остальные процентные бонусы из способностей суммируются ([Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed)).
- Плоские: Wind Lace +15 (бонусы нескольких Wind Lace не стакаются) ([id 244](https://www.dota2.com/datafeed/itemdata?language=english&item_id=244)); Eul's +20 ([id 100](https://www.dota2.com/datafeed/itemdata?language=english&item_id=100)); Wind Waker +30 ([датафид-предметы](https://www.dota2.com/datafeed/itemdata?language=english&item_id=100)).
- **Замедления**: процентные замедления из разных источников суммируются с процентными бонусами (аддитивно) в общий множитель; одинаковые экземпляры одного источника не стакаются, а обновляют длительность ([Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed); [Fandom Slow](https://dota2.fandom.com/wiki/Slow); [обсуждение r/learndota2](https://www.reddit.com/r/learndota2/comments/hkjnye/how_do_move_speed_slows_work)) `(не проверено для 7.41f)` — страницу Liquipedia Move Speed Slow прочитать не удалось (блокировка по частоте запросов).
- Исключения нестакания среди замедлений: Orb of Frost, Orb of Corrosion и Eye of Skadi не стакаются между собой (7.39) ([оф. 7.39](https://www.dota2.com/datafeed/patchnotes?version=7.39&language=english)).
- **Slow Resistance** уменьшает силу замедления и поднимает минимальную скорость на свой процент (7.38) — см. раздел 9 ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english)).
- **Hex** и «set movement speed» (Helm of the Dominator и т. п.) задают базу, другие бонусы всё ещё действуют в пределах лимитов; «absolute» эффекты (Phoenix Sun Ray и т. д.) не изменяются ничем, кроме haste ([Liquipedia Movement Speed](https://liquipedia.net/dota2/Movement_Speed)).
- Silver Edge Shadow Walk при ударе ограничивает максимальную скорость цели до 200 (не диспеллится, не пробивает Debuff Immunity) ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)).
- База скорости героев: 275–330 ([датафид-герои](https://www.dota2.com/datafeed/herodata?language=english&hero_id=8), расчёт по 127 героям).

### Частые ошибки

- «Минимальная скорость 0/50» — 100 по умолчанию (выше при Slow Resistance).
- «Максимум 550 — жёсткий предел для всех» — есть способы обойти (Windrunner 600, Thirst и др.; Force Boots — убранный нейтральный предмет).
- «Ночью +скорость» — убрано с 7.38.
- «Две пары ботинок дают сумму скоростей» — нет.
- «Yasha и Manta дают скорость вместе» — нет, Yasha-based не стакается.
- «Slow Resistance 20% уменьшает замедление 50% до 30%» — нет: 50% × (1−0.2) = 40%.
- «Статус-сопротивление уменьшает силу замедления» — с 7.34 нет.

### Что это значит для покупок

- Один комплект ботинок; несколько дорогих Yasha-based предметов ради скорости не нужны.
- Против героев с замедлениями Sange-based/Abyssal/Disperser дают Slow Resistance и поднимают минимум скорости.
- Force Boots нет в пуле нейтральных предметов 7.41f; лимит 550 обходят способностями героев.

---

## Список фактов, не проверенных для 7.41f

1. Attribute Bonus (кнопка +атрибуты): Liquipedia/заметки говорят +2 ко всем атрибутам на уровень (7 уровней), датафид показывает `attribute_bonus_all`=4 и `max_level`=4 — расхождение не объяснено.
2. Максимум скорости атаки 700 и минимум 20: источник Liquipedia (страница устарела относительно 7.38), официально подтверждена только смена отображения без геймплейных изменений.
3. Базовая скорость атаки 100 у большинства героев и значения у отдельных героев: Liquipedia.
4. «Negation»-эффекты брони (Natural Order, Marksmanship, Infernal Shred) уменьшают только основную броню: Liquipedia, текущие числа не сверены.
5. Корупция брони от талантов (2.5–5 на 10 с) и атрибуты Reinforced/Piercing/Runty (7.31): Liquipedia.
6. Эфирные источники не стакаются (берётся максимум), магсопротивление иллюзий = 0, Natural Order обнуляет базу: Liquipedia.
7. Список пробивающих Debuff Immunity источников Break (Viper Strike, Nyx Vendetta Shard, PA Fan of Knives Scepter, Shadow Demon Demonic Purge Scepter): Liquipedia.
8. «Гарантированный True Strike» у Parasma/Witch Blade/Silver Edge: только Liquipedia (шансы Javelin/Maelstrom/Mjollnir/MKB/Bloodthorn подтверждены датафидом).
9. Точная формула объединения Incoming Heal Amplification и Health Restoration в 7.41: заметки дают только словесное описание.
10. Стакаются ли друг с другом Slow Resistance Sange-based предметов.
11. Slow Resistance и стаки: правило «процентные замедления из разных источников суммируются» — Liquipedia Movement Speed + Fandom + Reddit; страница Liquipedia Move Speed Slow не была прочитана.
12. Trident: в датафиде нет описания и рецепта; значения 30% SR/spell amp приведены как есть.
13. Порядок применения lifesteal-источников и Health Restoration (аддитивно, затем множитель): Liquipedia, страница частично устарела.
14. Haste Rune = 550: Liquipedia Runes (официальных заметок на значение нет; длительность 22 с — официально).
15. +1 к скорости атаки за очко Agility: только Liquipedia (в датафиде и заметках 7.33–7.41f числа нет); тот же статус у «скорости атаки 100 базово» и пределов 20/700 (пп. 2–3).
16. Число Universal-героев и конкретный список: не проверялся (датафид показывает 22, Liquipedia 23).

## Конфликты Liquipedia и официальных источников

1. **Slow Resistance предметов**: Liquipedia (Sange 20%, Abyssal 25%, Sange and Yasha / Kaya and Sange 25%) устарела; в 7.41 Sange 25%, Abyssal 30%, Sange and Yasha 30% (датафид + [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)). Приоритет — официальные.
2. **Sange and Yasha**: Liquipedia пишет Status Resistance 16% (верно), но Slow Resistance 25% (устарело; 30% в 7.41).
3. **Nullifier и неуязвимость**: примечание в датафиде-предмете «Can be cast on invulnerable units» противоречит официальной заметке 7.40 «Nullifier's Nullify can no longer target invulnerable units» ([оф. 7.40](https://www.dota2.com/datafeed/patchnotes?version=7.40&language=english)). Приоритет — заметка 7.40; текст описания предмета, вероятно, не обновлён.
4. **Health Restoration (Liquipedia)**: на странице формулы 7.39 для Heal manipulation описаны отдельно от Health Restoration; официальное 7.41 изменило взаимодействие (входящее усиление хилов теперь убывающе с Health Restoration, исходящее — отдельно). Liquipedia отразила изменение 7.41 только в таблице изменений, не в тексте.
5. **Attack Speed (Liquipedia)**: страница не учитывает 7.38 («Attack Speed Display is no longer normalized to 1.7 BAT»); часть таблиц «Range (in 1.7 BAT Representation)» относится к старому отображению.
6. **Spell Lifesteal vs pure damage**: Liquipedia (talent text) говорит «heals from all 3 damage types», а общая часть страницы и [оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english) — «neither applies to pure damage». Приоритет — 7.38.
7. **Spell Lifesteal против крипов**: Liquipedia 20% от значения против героев = −80% (согласуется с 7.38).
8. **Предметные цифры на страницах Liquipedia** (Armor/Magic Resistance/Attack Speed): значения многих предметов (Pavise, Cloak 18, Meteor Hammer и др.) могут отставать от 7.41f; использовались числа датафида.
9. **Universal damage per attribute** в существующем `formulas.json`: там стоит 0.7 с пометкой verify; по официальным заметкам правильно **0.45** ([оф. 7.38](https://www.dota2.com/datafeed/patchnotes?version=7.38&language=english); [оф. 7.41](https://www.dota2.com/datafeed/patchnotes?version=7.41&language=english)).
10. **Magic Resistance of BKB**: в [оф. 7.33](https://www.dota2.com/datafeed/patchnotes?version=7.33&language=english) указано 50%; официально повышено до 60% в 7.35c ([оф. 7.35c](https://www.dota2.com/datafeed/patchnotes?version=7.35c&language=english)); датафид — 60%.
