# Расхождения официального datafeed и dotaconstants

Официальный слой: патч 7.41f (datafeed от 2026-10-01). dotaconstants: последний патч в patch.json — 7.41 (2026-03-24).
Слева старое значение dotaconstants, справа официальное. «Относительное изменение» = |новое - старое| / max(старое, 1).

## Сводка

- предметы: цена отличается у 1, состав (компоненты) у 4, КД/мана у 1, числовые значения у 0; только в официальном слое 44, только в dotaconstants 1
- герои: расхождений базовых характеристик 0 (у 0 героев из 127)
- способности: КД/мана 1, значения 0, новых способностей 5, исчезнувших 53; наборы талантов отличаются у 2 героев

Сколько сравнено: предметов 301, числовых значений предметов 1037, параметров героев 1905, способностей 734, числовых значений способностей 4427.

## Вывод о свежести

Кэш dotaconstants уже соответствует патчу 7.41f (хотя patch.json заканчивается на 7.41). Проверка по заметкам 7.41f (предметы с изменением цены):

| предмет | цена в dotaconstants | цена официально | заметка 7.41f |
|---|---|---|---|
| greater_crit | 5200 | 5200 | Recipe cost increased from 900 to 1000. Total cost increased from 5100g to 5200g |
| dragon_lance | 2000 | 2000 | Recipe cost increased from 450 to 550. Total cost increased from 1900g to 2000g |
| heart | 5300 | 5300 | Recipe cost increased from 700 to 800. Total cost increased from 5200g to 5300g |
| heavens_halberd | 3300 | 3300 | Recipe cost decreased from 450 to 350. Total cost decreased from 3400g to 3300g |
| hurricane_pike | 4550 | 4550 | Total cost increased from 4450g to 4550g (due to Dragon Lance cost increase) |
| hydras_breath | 5900 | 5900 | Recipe cost decreased from 1100 to 1000. Total cost unchanged at 5900g (due to Dragon Lance cost increase) |
| octarine_core | 5100 | 5100 | Recipe cost increased from 200 to 400. Total cost increased from 4900g to 5100g |

## Топ-20 расхождений по относительному изменению

| # | что | расхождение | относит. изменение |
|---|---|---|---|
| 1 | способность disruptor_kinetic_fence | КД 0 -> 14 | 1400% |
| 2 | предмет recipe_iron_talon | цена 125 -> 1 | 99% |
| 3 | предмет basher | КД 2 -> 2.3 | 15% |

## Предметы: цена

| предмет | dotaconstants | официально |
|---|---|---|
| recipe_iron_talon | 125 | 1 |

## Предметы: состав

| предмет | dotaconstants | официально |
|---|---|---|
| dagon_2 | - | dagon, recipe_dagon |
| dagon_3 | - | dagon_2, recipe_dagon |
| dagon_4 | - | dagon_3, recipe_dagon |
| dagon_5 | - | dagon_4, recipe_dagon |

## Предметы: КД и мана

| предмет | параметр | dotaconstants | официально |
|---|---|---|---|
| basher | КД | 2 | 2.3 |

## Предметы: числовые значения

| предмет | значение | dotaconstants | официально |
|---|---|---|---|

## Предметы: есть только с одной стороны

Только в официальном слое (продаются или рецепты, не нейтральные): recipe_angels_demise, recipe_bloodstone, recipe_boots_of_bearing, recipe_butterfly, recipe_dagon_2, recipe_dagon_3, recipe_dagon_4, recipe_dagon_5, recipe_desolator, recipe_echo_sabre, recipe_fallen_sky, recipe_great_famango, recipe_greater_famango, recipe_hood_of_defiance, recipe_invis_sword, recipe_kaya_and_sange, recipe_maelstrom, recipe_mage_slayer, recipe_mask_of_madness, recipe_medallion_of_courage, recipe_moon_shard, recipe_necronomicon_2, recipe_necronomicon_3, recipe_nullifier, recipe_oblivion_staff, recipe_orb_of_corrosion, recipe_pers, recipe_phase_boots, recipe_poor_mans_shield, recipe_power_treads, recipe_radiance, recipe_rapier, recipe_ring_of_aquila, recipe_sange_and_yasha, recipe_satanic, recipe_skadi, recipe_soul_booster, recipe_tranquil_boots, recipe_travel_boots_2, recipe_ultimate_scepter, recipe_vanguard, recipe_vladmir, recipe_ward_dispenser, recipe_yasha_and_kaya

Только в dotaconstants (не нейтральные, с ценой): diffusal_blade_2

## Герои: базовые характеристики

| герой | параметр | dotaconstants | официально |
|---|---|---|---|

## Способности: КД и мана

| герой | способность | параметр | dotaconstants | официально |
|---|---|---|---|---|
| disruptor | disruptor_kinetic_fence | КД | 0 | 14 |

## Способности: значения

| герой | способность | значение | dotaconstants | официально |
|---|---|---|---|---|

## Способности: новые и исчезнувшие

Новые в официальном слое: ringmaster:ringmaster_dark_carnival_souvenirs, ringmaster:ringmaster_funhouse_mirror, ringmaster:ringmaster_strongman_tonic, ringmaster:ringmaster_whoopee_cushion, ringmaster:ringmaster_summon_unicycle

Исчезли (есть в dotaconstants, нет в официальном): bane:bane_nightmare_end, crystal_maiden:crystal_maiden_freezing_field_stop, morphling:morphling_morph_replicate, puck:puck_ethereal_jaunt, windrunner:windrunner_focusfire_cancel, kunkka:kunkka_return, tinker:tinker_keen_teleport, dazzle:dazzle_nothl_projection_end, rattletrap:rattletrap_jetpack_toggle, life_stealer:life_stealer_consume, batrider:batrider_sticky_napalm_application_damage, spectre:spectre_reality, ancient_apparition:ancient_apparition_ice_blast_release, doom_bringer:doom_bringer_empty1, doom_bringer:doom_bringer_empty2, alchemist:alchemist_unstable_concoction_throw, invoker:invoker_empty1, invoker:invoker_empty2, shadow_demon:shadow_demon_shadow_poison_release, rubick:rubick_empty1, rubick:rubick_empty2, rubick:rubick_telekinesis_land, rubick:rubick_telekinesis_land_self, nyx_assassin:nyx_assassin_unburrow, naga_siren:naga_siren_reel_in, naga_siren:naga_siren_song_of_the_siren_cancel, keeper_of_the_light:keeper_of_the_light_illuminate_end, wisp:wisp_tether_break, visage:visage_stone_form_self_cast, visage:visage_summon_familiars_stone_form, centaur:centaur_mount, shredder:shredder_return_chakram, tusk:tusk_launch_snowball, elder_titan:elder_titan_move_spirit, elder_titan:elder_titan_return_spirit, techies:techies_reactive_tazer_stop, techies:techies_focused_detonate, phoenix:phoenix_sun_ray_toggle_move, phoenix:phoenix_launch_fire_spirit, phoenix:phoenix_icarus_dive_stop, phoenix:phoenix_sun_ray_stop, oracle:oracle_diviners_deck, monkey_king:monkey_king_primal_spring, monkey_king:monkey_king_primal_spring_early, monkey_king:monkey_king_untransform, pangolier:pangolier_gyroshell_stop, pangolier:pangolier_rollup_stop, hoodwink:hoodwink_sharpshooter_release, ringmaster:ringmaster_empty_souvenir, ringmaster:ringmaster_tame_the_beasts_crack, dawnbreaker:dawnbreaker_converge, primal_beast:primal_beast_onslaught_release, kez:kez_shodo_sai_parry_cancel

## Таланты: наборы отличаются

| герой | новые таланты | исчезнувшие таланты |
|---|---|---|
| rubick | - | rubick_hidden3, rubick_hidden4, rubick_hidden5 |
| ringmaster | - | ringmaster_dark_carnival_souvenirs, ringmaster_funhouse_mirror, ringmaster_strongman_tonic, ringmaster_summon_unicycle, ringmaster_whoopee_cushion |
