# 数据台账（自动生成）

根目录: `data\raw`

批次目录数: 1088
文件数: 138887
字节数: 135,634,263,041

## 按来源汇总

| 来源 | 批次目录 | 文件数 | 体积 |
|---|---:|---:|---:|
| baostock | 19 | 17,805 | 1.87 GiB |
| bigquant | 16 | 14,004 | 69.26 GiB |
| em_fin | 125 | 250 | 0.01 GiB |
| etf-minute-probe | 1 | 5 | 0.00 GiB |
| hf_minute_1m | 1 | 4 | 0.01 GiB |
| sina | 252 | 504 | 0.05 GiB |
| sina_industries | 4 | 8 | 0.00 GiB |
| sina_universe | 280 | 560 | 0.01 GiB |
| ths | 71 | 142 | 0.01 GiB |
| tushare | 46 | 35,757 | 4.31 GiB |
| tx | 193 | 771 | 0.03 GiB |
| user_csv_1m | 3 | 7 | 0.00 GiB |
| user_dataset | 2 | 6 | 1.98 GiB |
| user_minute_1m | 12 | 2,433 | 35.67 GiB |
| xiaodefa | 63 | 66,631 | 13.11 GiB |

## 明细

### baostock

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `baostock/20260905_225721` | 32 | 2.7 MiB | .csv×16, .json×16 | board_bj_430047.csv … stsusp_sz_000792.meta.json | - |
| `baostock/20260905_230017` | 67 | 3.0 MiB | .json×34, .csv×33 | adjust_sh_600519.csv … trade_dates.meta.json | - |
| `baostock/adjust_factor` | 686 | 0.2 MiB | .csv×343, .json×343 | sh.600000.csv … sz.300799.csv.meta.json | - |
| `baostock/daily` | 11,104 | 1,867.4 MiB | .csv×5552, .json×5552 | sh.600000.csv … sz.302132.csv.meta.json | - |
| `baostock/intraday-t0-20260914` | 2 | 0.1 MiB | .csv×1, .json×1 | sh_000300_2021-08-05_2024-12-31_d.csv … sh_000300_2021-08-05_2024-12-31_d.meta.json | - |
| `baostock/intraday-t0-opportunity-20260914` | 1 | 0.0 MiB | .json×1 | fetch_log.json | - |
| `baostock/lowturn-dynamic-minute-full-20260912-1` | 166 | 0.7 MiB | .csv×166 | sh_600000_2020-05-06_f5.csv … sz_002493_2020-05-06_f5.csv | - |
| `baostock/lowturn-dynamic-minute-full-20260912-2` | 159 | 0.7 MiB | .csv×159 | sh_600000_2021-09-01_f5.csv … sz_000617_2022-12-01_f5.csv | - |
| `baostock/minute` | 4,714 | 10.8 MiB | .csv×2357, .json×2357 | l2repair_sh_600009_2020-03-02_f5.csv … target_sz_301361_2024-06-13_f5.csv.meta.json | - |
| `baostock/pv1-blend-dynamic-minute-20260912-1` | 354 | 1.5 MiB | .csv×354 | sh_600039_2021-06-01_f5.csv … sz_300712_2020-07-01_f5.csv | - |
| `baostock/rev11-dynamic-minute-first-20260912-1` | 6 | 0.0 MiB | .csv×6 | sh_603536_2020-02-03_f5.csv … sz_300707_2020-02-03_f5.csv | - |
| `baostock/rev11-dynamic-minute-full-20260912-1` | 401 | 1.7 MiB | .csv×401 | sh_600007_2021-06-01_f5.csv … sz_300845_2022-12-01_f5.csv | - |
| `baostock/rev11-minute-probe-20260912-1` | 21 | 0.1 MiB | .csv×20, .json×1 | manifest.json … sz_300727_2020-12-01_f5.csv | - |
| `baostock/t0-minute-evidence-20260911` | 3 | 0.1 MiB | .json×3 | analysis_summary_20260911.json … sample_manifest.json | - |
| `baostock/t0-minute-evidence-20260911/daily` | 40 | 0.6 MiB | .csv×20, .json×20 | sh_600062_daily.csv … sz_301168_daily.csv.meta.json | - |
| `baostock/t0-minute-evidence-20260911/minute` | 40 | 25.8 MiB | .csv×20, .json×20 | sh_600062_2023_f5adj.csv … sz_301168_2023_f5adj.csv.meta.json | - |
| `baostock/ten-year-repair-20260913-1` | 2 | 0.0 MiB | .json×1, .csv×1 | patches.json … sz.300712_2020-11-02_f5.csv | - |
| `baostock/ten-year-repair-20260913-2` | 5 | 0.0 MiB | .csv×4, .json×1 | manifest.json … sz.300536_2020-10-09_f5.csv | - |
| `baostock/ten-year-repair-20260913-3` | 2 | 0.0 MiB | .json×1, .csv×1 | patches.json … sz.300727_2020-12-01_f5.csv | - |

### bigquant

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `bigquant/intraday-t0-20260914` | 15 | 21.5 MiB | .csv×9, .json×6 | 000300.SH_2021-08-05_2021-12-31_bar1m.csv … sh_000300_2024-01-01_2024-12-31_f5.meta.json | - |
| `bigquant/minute-bulk-20260915-1/manifest` | 2 | 0.0 MiB | .json×2 | extract-summary.json … zips.sha256.json | - |
| `bigquant/minute-bulk-20260915-1/manifest/years` | 4 | 0.1 MiB | .txt×4 | 2010.sha256.txt … 2013.sha256.txt | - |
| `bigquant/minute-bulk-20260915-1/years/2010` | 242 | 1,793.1 MiB | .parquet×242 | 20100104.parquet … 20101231.parquet | - |
| `bigquant/minute-bulk-20260915-1/years/2011` | 244 | 1,957.6 MiB | .parquet×244 | 20110104.parquet … 20111230.parquet | - |
| `bigquant/minute-bulk-20260915-1/years/2012` | 243 | 2,000.2 MiB | .parquet×243 | 20120104.parquet … 20121231.parquet | - |
| `bigquant/minute-bulk-20260915-1/years/2013` | 238 | 2,116.6 MiB | .parquet×238 | 20130104.parquet … 20131231.parquet | - |
| `bigquant/minute-bulk-20260915-1/years/2014` | 245 | 2,206.0 MiB | .parquet×245 | 20140102.parquet … 20141231.parquet | - |
| `bigquant/minute-bulk-20260915-1/years/2015` | 2,607 | 10,931.7 MiB | .csv×2607 | sh600000_2015.csv … sz302132_2015.csv | - |
| `bigquant/minute-bulk-20260915-1/years/2016` | 2,834 | 12,022.5 MiB | .csv×2834 | sh600000_2016.csv … sz302132_2016.csv | - |
| `bigquant/minute-bulk-20260915-1/years/2018` | 3,370 | 15,012.9 MiB | .csv×3370 | sh600000_2018.csv … sz302132_2018.csv | - |
| `bigquant/minute-bulk-20260915-1/years/2019` | 3,572 | 16,120.8 MiB | .csv×3572 | sh600000_2019.csv … sz302132_2019.csv | - |
| `bigquant/minute-bulk-20260915-1/years/2025` | 243 | 5,275.8 MiB | .parquet×243 | 20250102.parquet … 20251231.parquet | - |
| `bigquant/minute-bulk-20260915-1/years/2026` | 63 | 1,452.0 MiB | .parquet×63 | 20260105.parquet … 20260410.parquet | - |
| `bigquant/minute-check-20260914-1` | 78 | 10.1 MiB | .csv×77, .json×1 | 2015-01-05.csv … manifest.json | - |
| `bigquant/minute-repairs-20260914-1` | 4 | 0.0 MiB | .csv×3, .json×1 | patches.json … sz.300420_2019-09-02_f5.csv | - |

### em_fin

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `em_fin/sh600030/20260904T013245` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600110/20260904T013306` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600150/20260904T013254` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600172/20260904T013249` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600176/20260904T013210` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600183/20260904T013210` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600186/20260904T013239` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600276/20260904T013230` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600397/20260904T013259` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600487/20260904T013208` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600519/20260904T013230` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600519/20260904T013638` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600584/20260904T013213` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600664/20260904T013237` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600869/20260904T013239` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600900/20260904T013251` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600988/20260904T013242` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh600989/20260904T013307` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601138/20260904T013215` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601179/20260904T080501` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601179/20260904T080803` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601208/20260904T013235` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601212/20260904T013539` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601318/20260904T013236` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601398/20260904T013245` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601718/20260904T212449` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601869/20260904T013221` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh601899/20260904T013212` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603083/20260904T013227` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603186/20260904T013227` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603228/20260904T013233` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603256/20260904T013246` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603259/20260904T013211` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603538/20260904T013304` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603618/20260904T013250` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603629/20260904T013223` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603799/20260904T013253` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603893/20260904T013250` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603986/20260904T013207` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603987/20260904T212438` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh603993/20260904T013229` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688008/20260904T013214` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688012/20260904T013216` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688017/20260904T013247` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688041/20260904T013219` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688048/20260904T013538` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688072/20260904T013229` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688110/20260904T013300` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688143/20260904T013246` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688146/20260904T013228` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688167/20260904T013243` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688183/20260904T013259` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688195/20260904T013256` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688205/20260904T013307` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688256/20260904T013209` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688300/20260904T013247` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688313/20260904T013233` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688347/20260904T013226` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688361/20260904T013238` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688498/20260904T013218` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688521/20260904T013235` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688525/20260904T013218` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688627/20260904T013252` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688702/20260904T013243` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688766/20260904T013217` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sh688981/20260904T013222` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000100/20260904T013255` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000338/20260904T013253` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000506/20260904T013256` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000636/20260904T013212` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000657/20260904T013217` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000703/20260904T013259` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000811/20260904T013303` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz000988/20260904T013226` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz001309/20260904T013216` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002008/20260904T013228` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002080/20260904T013244` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002081/20260904T013303` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002131/20260904T013249` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002384/20260904T013209` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002407/20260904T013220` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002428/20260904T013213` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002437/20260904T013244` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002536/20260904T013256` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002558/20260904T013305` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002580/20260904T013540` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002594/20260904T013539` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002716/20260904T013241` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002821/20260904T013257` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002837/20260904T013251` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002851/20260904T013232` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz002916/20260904T013240` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300058/20260904T013224` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300189/20260904T013302` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300274/20260904T013219` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300285/20260904T013215` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300308/20260904T013207` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300394/20260904T013208` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300395/20260904T013254` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300454/20260904T013258` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300475/20260904T013224` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300476/20260904T013211` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300489/20260904T013237` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300502/20260904T013207` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300548/20260904T013238` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300570/20260904T013234` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300604/20260904T013225` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300620/20260904T013231` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300666/20260904T013231` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300672/20260904T013305` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300684/20260904T013257` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300750/20260904T013214` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300757/20260904T013232` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300759/20260904T013234` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300857/20260904T013223` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz300903/20260904T013252` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301018/20260904T013301` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301165/20260904T013242` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301171/20260904T013248` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301217/20260904T013225` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301308/20260904T013220` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301396/20260904T013240` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301511/20260904T013236` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301526/20260904T013222` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `em_fin/sz301536/20260904T013306` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |

### etf-minute-probe

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `etf-minute-probe/20260909_etf_m5_probe` | 5 | 0.1 MiB | .raw×4, .json×1 | sh510300_eastmoney.raw … sz159915_sina.raw | - |

### hf_minute_1m

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `hf_minute_1m/20260913-probe` | 4 | 9.9 MiB | .parquet×1, .csv×1, .json×1, .md×1 | 000607.parquet … probe-review.json | - |

### sina

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `sina/sh510050/20260903T035518` | 2 | 0.5 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510050/20260904T165015` | 2 | 0.5 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510050/20260904T185651` | 2 | 0.5 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510300/20260903T035519` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510300/20260904T165009` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510300/20260904T185625` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510500/20260903T035519` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510500/20260904T165011` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510500/20260904T185633` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510880/20260903T035526` | 2 | 0.5 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510880/20260904T165024` | 2 | 0.5 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh510880/20260904T185713` | 2 | 0.5 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512010/20260903T035522` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512010/20260904T165025` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512010/20260904T185717` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512100/20260903T035520` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512100/20260904T165010` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512100/20260904T185628` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512170/20260904T165022` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512170/20260904T185705` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512200/20260904T165041` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512200/20260904T185757` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512400/20260903T035523` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512400/20260904T165013` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512400/20260904T185644` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512480/20260903T035522` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512690/20260903T035521` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512690/20260904T165028` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512690/20260904T185723` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512710/20260904T165034` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512710/20260904T185741` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512800/20260903T035523` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512800/20260904T165017` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512800/20260904T185656` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512880/20260903T035521` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512880/20260904T165012` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512880/20260904T185637` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512890/20260904T165018` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512890/20260904T185659` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512980/20260904T165033` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh512980/20260904T185736` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh513100/20260903T035525` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515030/20260904T165040` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515030/20260904T185753` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515170/20260904T165045` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515170/20260904T185806` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515210/20260904T165042` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515210/20260904T185759` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515220/20260904T165020` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515220/20260904T185701` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515790/20260903T035524` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515790/20260904T165036` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515790/20260904T185745` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515800/20260904T165043` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515800/20260904T185802` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515880/20260904T165008` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh515880/20260904T185620` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516150/20260904T165038` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516150/20260904T185749` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516160/20260903T035524` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516510/20260904T165037` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516510/20260904T185747` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516970/20260904T165049` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh516970/20260904T185814` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh517520/20260904T165015` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh517520/20260904T185652` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh518880/20260903T035525` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh518880/20260904T165006` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh518880/20260904T185612` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh560080/20260904T165047` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh560080/20260904T185810` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh560170/20260904T165051` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh560170/20260904T185815` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh560280/20260904T165040` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh560280/20260904T185754` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh561360/20260904T165046` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh561360/20260904T185806` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh562800/20260904T165034` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh562800/20260904T185738` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh563300/20260904T165019` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh563300/20260904T185700` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh588000/20260904T165005` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh588000/20260904T185608` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh588170/20260904T080515` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh588170/20260904T165004` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh588220/20260904T165021` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh588220/20260904T185703` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600030/20260904T012630` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600110/20260904T012833` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600150/20260904T012722` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600172/20260904T012648` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600176/20260904T012316` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600183/20260904T012319` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600186/20260904T012557` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600276/20260904T012505` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600397/20260904T012756` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600487/20260904T012306` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600519/20260904T012509` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600519/20260904T013637` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600584/20260904T012342` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600664/20260904T012548` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600869/20260904T012601` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600900/20260904T012702` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600988/20260904T012615` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh600989/20260904T012836` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601138/20260904T012350` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601179/20260904T080500` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601179/20260904T080802` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601208/20260904T012535` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601212/20260904T012802` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601318/20260904T012539` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601398/20260904T012634` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601718/20260904T212448` | 2 | 0.4 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601869/20260904T012421` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh601899/20260904T012334` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603083/20260904T012447` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603186/20260904T012450` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603228/20260904T012523` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603256/20260904T012637` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603259/20260904T012322` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603538/20260904T012822` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603618/20260904T012656` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603629/20260904T012426` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603799/20260904T012715` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603893/20260904T012658` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603986/20260904T012258` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603987/20260904T212437` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh603993/20260904T012459` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688008/20260904T012347` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688012/20260904T012357` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688017/20260904T012643` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688041/20260904T012413` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688048/20260904T012616` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688072/20260904T012501` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688110/20260904T012759` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688143/20260904T012638` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688146/20260904T012451` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688167/20260904T012619` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688183/20260904T012757` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688195/20260904T012736` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688205/20260904T012837` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688256/20260904T012308` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688300/20260904T012641` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688313/20260904T012524` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688347/20260904T012444` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688361/20260904T012549` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688498/20260904T012405` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688521/20260904T012532` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688525/20260904T012407` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688627/20260904T012707` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688702/20260904T012617` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688766/20260904T012400` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sh688981/20260904T012423` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000100/20260904T012730` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000338/20260904T012711` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000506/20260904T012740` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000636/20260904T012330` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000657/20260904T012404` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000703/20260904T012752` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000811/20260904T012815` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz000988/20260904T012444` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz001309/20260904T012358` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002008/20260904T012455` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002080/20260904T012623` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002081/20260904T012811` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002131/20260904T012652` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002384/20260904T012312` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002407/20260904T012417` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002428/20260904T012338` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002437/20260904T012627` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002536/20260904T012734` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002558/20260904T012829` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002580/20260904T012819` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002594/20260904T012726` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002716/20260904T012609` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002821/20260904T012742` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002837/20260904T012705` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002851/20260904T012520` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz002916/20260904T012605` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159301/20260904T165051` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159301/20260904T185816` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159530/20260904T165020` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159530/20260904T185702` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159565/20260904T165050` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159565/20260904T185815` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159611/20260904T165029` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159611/20260904T185726` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159732/20260904T165030` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159732/20260904T185728` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159745/20260904T165048` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159745/20260904T185812` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159755/20260904T165031` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159755/20260904T185730` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159766/20260904T165039` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159766/20260904T185751` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159819/20260904T165026` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159819/20260904T185719` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159852/20260904T165023` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159852/20260904T185707` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159865/20260904T165035` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159865/20260904T185743` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159869/20260904T165027` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159869/20260904T185720` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159870/20260904T165028` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159870/20260904T185725` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159915/20260903T035520` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159915/20260904T165007` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159915/20260904T185618` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159949/20260903T042346` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159949/20260904T165013` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159949/20260904T185641` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159985/20260904T165032` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159985/20260904T185733` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159992/20260904T165016` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159992/20260904T185653` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159996/20260904T165046` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159996/20260904T185808` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159998/20260904T165044` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz159998/20260904T185804` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300058/20260904T012432` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300189/20260904T012807` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300274/20260904T012411` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300285/20260904T012354` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300308/20260904T012251` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300394/20260904T012302` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300395/20260904T012718` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300454/20260904T012748` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300475/20260904T012435` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300476/20260904T012326` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300489/20260904T012544` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300502/20260904T012255` | 2 | 0.3 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300548/20260904T012553` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300570/20260904T012527` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300604/20260904T012438` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300620/20260904T012511` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300666/20260904T012514` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300672/20260904T012825` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300684/20260904T012745` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300750/20260904T012345` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300757/20260904T012517` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300759/20260904T012530` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300857/20260904T012428` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz300903/20260904T012706` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301018/20260904T012803` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301165/20260904T012611` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301171/20260904T012645` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301217/20260904T012440` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301308/20260904T012418` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301396/20260904T012602` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301511/20260904T012540` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301526/20260904T012422` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `sina/sz301536/20260904T012829` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |

### sina_industries

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `sina_industries/nodes/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_industries/nodes/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_industries/nodes/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_industries/nodes/20260904T011651` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |

### sina_universe

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `sina_universe/page000/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page000/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page000/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page000/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page000/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page001/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page001/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page001/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page001/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page001/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page002/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page002/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page002/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page002/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page002/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page003/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page003/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page003/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page003/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page003/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page004/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page004/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page004/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page004/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page004/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page005/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page005/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page005/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page005/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page005/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page006/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page006/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page006/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page006/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page006/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page007/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page007/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page007/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page007/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page007/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page008/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page008/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page008/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page008/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page008/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page009/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page009/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page009/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page009/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page009/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page010/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page010/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page010/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page010/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page010/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page011/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page011/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page011/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page011/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page011/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page012/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page012/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page012/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page012/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page012/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page013/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page013/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page013/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page013/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page013/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page014/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page014/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page014/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page014/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page014/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page015/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page015/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page015/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page015/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page015/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page016/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page016/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page016/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page016/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page016/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page017/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page017/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page017/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page017/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page017/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page018/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page018/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page018/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page018/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page018/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page019/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page019/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page019/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page019/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page019/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page020/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page020/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page020/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page020/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page020/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page021/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page021/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page021/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page021/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page021/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page022/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page022/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page022/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page022/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page022/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page023/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page023/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page023/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page023/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page023/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page024/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page024/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page024/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page024/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page024/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page025/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page025/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page025/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page025/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page025/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page026/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page026/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page026/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page026/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page026/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page027/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page027/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page027/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page027/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page027/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page028/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page028/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page028/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page028/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page028/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page029/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page029/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page029/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page029/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page029/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page030/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page030/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page030/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page030/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page030/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page031/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page031/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page031/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page031/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page031/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page032/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page032/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page032/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page032/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page032/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page033/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page033/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page033/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page033/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page033/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page034/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page034/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page034/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page034/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page034/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page035/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page035/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page035/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page035/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page035/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page036/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page036/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page036/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page036/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page036/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page037/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page037/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page037/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page037/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page037/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page038/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page038/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page038/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page038/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page038/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page039/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page039/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page039/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page039/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page039/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page040/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page040/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page040/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page040/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page040/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page041/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page041/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page041/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page041/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page041/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page042/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page042/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page042/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page042/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page042/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page043/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page043/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page043/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page043/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page043/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page044/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page044/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page044/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page044/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page044/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page045/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page045/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page045/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page045/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page045/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page046/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page046/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page046/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page046/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page046/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page047/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page047/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page047/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page047/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page047/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page048/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page048/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page048/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page048/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page048/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page049/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page049/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page049/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page049/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page049/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page050/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page050/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page050/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page050/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page050/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page051/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page051/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page051/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page051/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page051/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page052/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page052/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page052/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page052/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page052/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page053/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page053/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page053/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page053/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page053/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page054/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page054/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page054/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page054/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page054/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page055/20260904T004903` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page055/20260904T005147` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page055/20260904T005518` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page055/20260904T010740` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |
| `sina_universe/page055/20260904T011650` | 2 | 0.0 MiB | .json×2 | meta.json … response.json | - |

### ths

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `ths/sh510050/20260903T040924` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510050/20260903T042255` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510300/20260903T040925` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510300/20260903T042252` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510500/20260903T040925` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510500/20260903T042253` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510880/20260903T040930` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh510880/20260903T042259` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512010/20260903T040927` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512010/20260903T042259` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512100/20260903T040926` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512100/20260903T042253` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512170/20260903T042258` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512200/20260903T042308` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512400/20260903T040928` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512400/20260903T042255` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512480/20260903T040927` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512690/20260903T040927` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512690/20260903T042301` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512710/20260903T042304` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512800/20260903T040928` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512800/20260903T042256` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512880/20260903T040926` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512880/20260903T042254` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512890/20260903T042256` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh512980/20260903T042303` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh513100/20260903T040930` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515030/20260903T042307` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515170/20260903T042309` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515210/20260903T042308` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515220/20260903T042257` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515790/20260903T040929` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515790/20260903T042305` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515800/20260903T042308` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh515880/20260903T042252` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh516150/20260903T042306` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh516160/20260903T040929` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh516510/20260903T042305` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh516970/20260903T042311` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh517520/20260903T042255` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh518880/20260903T040930` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh518880/20260903T042251` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh560080/20260903T042310` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh560170/20260903T042312` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh560280/20260903T042307` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh561360/20260903T042309` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh562800/20260903T042303` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh563300/20260903T042257` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh588000/20260903T042251` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh588170/20260903T042250` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sh588220/20260903T042258` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159301/20260903T042312` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159530/20260903T042258` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159565/20260903T042311` | 2 | 0.1 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159611/20260903T042301` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159732/20260903T042302` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159745/20260903T042311` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159755/20260903T042302` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159766/20260903T042306` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159819/20260903T042300` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159852/20260903T042259` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159865/20260903T042304` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159869/20260903T042300` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159870/20260903T042301` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159915/20260903T040926` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159915/20260903T042252` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159949/20260903T042254` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159985/20260903T042303` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159992/20260903T042256` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159996/20260903T042310` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |
| `ths/sz159998/20260903T042309` | 2 | 0.2 MiB | .json×2 | meta.json … response.json | - |

### tushare

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `tushare` | 2 | 0.1 MiB | .log×2 | fetch_20260909-r1.log … fetch_20260909-r3_console.log | - |
| `tushare/balancesheet/20260909-r3` | 5,900 | 292.3 MiB | .csv×5899, .json×1 | chunk_000001.SZ.csv … manifest.json | - |
| `tushare/balancesheet/20260910-r1` | 5 | 0.2 MiB | .csv×3, .log×1, .json×1 | chunk_000683.SZ.csv … manifest.json | - |
| `tushare/cashflow/20260909-r3` | 5,900 | 223.1 MiB | .csv×5899, .json×1 | chunk_000001.SZ.csv … manifest.json | - |
| `tushare/cashflow/20260910-r1` | 9 | 0.2 MiB | .csv×7, .log×1, .json×1 | chunk_001301.SZ.csv … manifest.json | - |
| `tushare/daily_basic` | 1 | 0.1 MiB | .log×1 | fetch_20260909-r1.log | - |
| `tushare/daily_basic/20260909-r1` | 1,867 | 1,215.3 MiB | .csv×1866, .json×1 | chunk_20190102.csv … manifest.json | 20190102..20260909 (1866) |
| `tushare/daily_basic/20260913-r2` | 977 | 383.1 MiB | .csv×975, .log×1, .json×1 | chunk_20150105.csv … manifest.json | 20150105..20181228 (975) |
| `tushare/disclosure_date` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r1.log | - |
| `tushare/disclosure_date/20260909-r1` | 32 | 6.7 MiB | .csv×31, .json×1 | chunk_period_20181231.csv … manifest.json | - |
| `tushare/dividend` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/dividend/20260909-r3` | 2,110 | 3.5 MiB | .csv×2109, .json×1 | chunk_20180102.csv … manifest.json | 20180102..20260909 (2109) |
| `tushare/dividend/20260913-r2` | 733 | 0.9 MiB | .csv×732, .json×1 | chunk_20150105.csv … manifest.json | 20150105..20171229 (732) |
| `tushare/events` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/express/20260909-r1` | 32 | 1.1 MiB | .csv×31, .json×1 | chunk_period_20181231.csv … manifest.json | - |
| `tushare/fina_indicator/20260909-r3` | 5,900 | 382.3 MiB | .csv×5899, .json×1 | chunk_000001.SZ.csv … manifest.json | - |
| `tushare/fina_indicator/20260910-r1` | 4 | 0.1 MiB | .csv×2, .log×1, .json×1 | chunk_000069.SZ.csv … manifest.json | - |
| `tushare/forecast/20260909-r1` | 98 | 34.0 MiB | .csv×97, .json×1 | chunk_201809.csv … manifest.json | - |
| `tushare/fund_basic/20260909-r1` | 3 | 9.9 MiB | .csv×2, .json×1 | chunk_market_E.csv … manifest.json | - |
| `tushare/income/20260909-r3` | 5,900 | 168.1 MiB | .csv×5899, .json×1 | chunk_000001.SZ.csv … manifest.json | - |
| `tushare/income/20260910-r1` | 4 | 0.1 MiB | .csv×2, .log×1, .json×1 | chunk_600482.SH.csv … manifest.json | - |
| `tushare/index_member_all` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r1.log | - |
| `tushare/index_member_all/20260909-r1` | 5 | 0.6 MiB | .csv×4, .json×1 | chunk_all.csv … manifest.json | - |
| `tushare/margin_detail/20260909-r1` | 1,867 | 485.8 MiB | .csv×1866, .json×1 | chunk_20190102.csv … manifest.json | 20190102..20260909 (1866) |
| `tushare/r3` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/repurchase` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/repurchase/20260909-r3` | 130 | 3.7 MiB | .csv×129, .json×1 | chunk_201601.csv … manifest.json | - |
| `tushare/share_float` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/share_float/20260909-r3` | 130 | 819.1 MiB | .csv×129, .json×1 | chunk_201601.csv … manifest.json | - |
| `tushare/statements` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/stk_holdertrade` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/stk_holdertrade/20260909-r3` | 130 | 14.1 MiB | .csv×129, .json×1 | chunk_201601.csv … manifest.json | - |
| `tushare/stock_basic` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/stock_basic/20260909-r3` | 4 | 0.2 MiB | .csv×3, .json×1 | chunk_D.csv … manifest.json | - |
| `tushare/sw_index_daily` | 2 | 0.0 MiB | .log×2 | fetch_20260909-r1.log … fetch_20260909-r3.log | - |
| `tushare/sw_index_daily/20260909-r1` | 32 | 4.0 MiB | .csv×31, .json×1 | chunk_801010.csv … manifest.json | - |
| `tushare/sw_index_daily/20260909-r2` | 32 | 4.0 MiB | .csv×31, .json×1 | chunk_801010.csv … manifest.json | - |
| `tushare/sw_index_daily/20260909-r3` | 33 | 10.8 MiB | .csv×32, .json×1 | chunk_801010.csv … manifest.json | - |
| `tushare/sw_index_daily/20260909-r4-verify` | 32 | 10.4 MiB | .csv×31, .json×1 | chunk_801010.csv … manifest.json | - |
| `tushare/sw_index_daily_l2` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r1.log | - |
| `tushare/sw_index_daily_l2/20260909-r1` | 132 | 30.6 MiB | .csv×131, .json×1 | chunk_801011.csv … manifest.json | - |
| `tushare/top_inst` | 1 | 0.0 MiB | .log×1 | fetch_20260909-r3.log | - |
| `tushare/top_inst/20260909-r3` | 1,867 | 285.9 MiB | .csv×1866, .json×1 | chunk_20190102.csv … manifest.json | 20190102..20260909 (1866) |
| `tushare/top_list` | 1 | 0.1 MiB | .log×1 | fetch_parallel_20260909-r1.log | - |
| `tushare/top_list/20260909-r1` | 1,867 | 27.0 MiB | .csv×1866, .json×1 | chunk_20190102.csv … manifest.json | 20190102..20260909 (1866) |
| `tushare/trade_cal/20260909-r1` | 4 | 0.1 MiB | .csv×2, .json×1, .log×1 | chunk_sse_20140101_20171231.csv … fetch_20260912-r2.log | - |

### tx

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `tx/sh510050/20260904T185651` | 8 | 0.3 MiB | .json×8 | meta.json … response_006.json | - |
| `tx/sh510300/20260904T185625` | 6 | 0.2 MiB | .json×6 | meta.json … response_004.json | - |
| `tx/sh510500/20260904T185633` | 6 | 0.2 MiB | .json×6 | meta.json … response_004.json | - |
| `tx/sh510880/20260904T185713` | 7 | 0.3 MiB | .json×7 | meta.json … response_005.json | - |
| `tx/sh512010/20260904T185716` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh512100/20260904T185628` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512170/20260904T185705` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512200/20260904T185756` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512400/20260904T185643` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512690/20260904T185723` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512710/20260904T185741` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512800/20260904T185656` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512880/20260904T185637` | 5 | 0.1 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh512890/20260904T185659` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh512980/20260904T185736` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh515030/20260904T185752` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh515170/20260904T185805` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh515210/20260904T185758` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh515220/20260904T185701` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh515790/20260904T185745` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh515800/20260904T185801` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh515880/20260904T185620` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh516150/20260904T185748` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh516510/20260904T185747` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh516970/20260904T185814` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh517520/20260904T185651` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh518880/20260904T185611` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh560080/20260904T185810` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh560170/20260904T185815` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh560280/20260904T185753` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh561360/20260904T185806` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh562800/20260904T185738` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh563300/20260904T185659` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh588000/20260904T185607` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh588170/20260904T080651` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh588170/20260904T213728` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh588220/20260904T185702` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh600030/20260904T012630` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600110/20260904T012833` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600150/20260904T012722` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600172/20260904T012648` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600176/20260904T012315` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600183/20260904T012319` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600183/20260904T012916` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600183/20260904T013145` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600186/20260904T012556` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600276/20260904T012504` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600397/20260904T012755` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600487/20260904T012306` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600519/20260904T012508` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600519/20260904T012925` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600519/20260904T013141` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600519/20260904T013637` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600584/20260904T012341` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600664/20260904T012547` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600869/20260904T012600` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600900/20260904T012701` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600988/20260904T012614` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh600989/20260904T012835` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh601138/20260904T012350` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh601179/20260904T080459` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601179/20260904T080802` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601208/20260904T012535` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601212/20260904T012801` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh601318/20260904T012539` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601398/20260904T012634` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601718/20260904T091546` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601718/20260904T212447` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh601869/20260904T012421` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh601899/20260904T012334` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh603083/20260904T012447` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603186/20260904T012449` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603228/20260904T012522` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603256/20260904T012637` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603259/20260904T012322` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603538/20260904T012821` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603618/20260904T012656` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh603629/20260904T012426` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603799/20260904T012714` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh603893/20260904T012657` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh603986/20260904T012258` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603987/20260904T091542` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603987/20260904T212436` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh603993/20260904T012459` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sh688008/20260904T012347` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh688012/20260904T012356` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh688017/20260904T012643` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688041/20260904T012412` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688048/20260904T012616` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688072/20260904T012501` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688110/20260904T012759` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688143/20260904T012638` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688146/20260904T012451` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688167/20260904T012618` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688183/20260904T012757` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688195/20260904T012735` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688205/20260904T012837` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688256/20260904T012308` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688300/20260904T012641` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sh688313/20260904T012524` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688347/20260904T012444` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh688361/20260904T012549` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688498/20260904T012405` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688521/20260904T012531` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688525/20260904T012407` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688627/20260904T012707` | 2 | 0.1 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh688702/20260904T012617` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sh688766/20260904T012400` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sh688981/20260904T012423` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz000100/20260904T012730` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000338/20260904T012710` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000338/20260904T012928` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000338/20260904T013148` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000506/20260904T012739` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000636/20260904T012330` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000657/20260904T012403` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000703/20260904T012751` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000811/20260904T012815` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz000988/20260904T012443` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz001309/20260904T012358` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz002008/20260904T012455` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002080/20260904T012622` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002081/20260904T012811` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002131/20260904T012652` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002384/20260904T012311` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002407/20260904T012416` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002428/20260904T012337` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002437/20260904T012626` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002536/20260904T012733` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002558/20260904T012828` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002580/20260904T012819` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002594/20260904T012726` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002716/20260904T012609` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz002821/20260904T012742` | 4 | 0.2 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz002837/20260904T012704` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz002851/20260904T012519` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz002916/20260904T012605` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz159301/20260904T185816` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sz159530/20260904T185702` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sz159565/20260904T185814` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sz159611/20260904T185726` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159732/20260904T185728` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159745/20260904T185812` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159755/20260904T185730` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159766/20260904T185750` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159819/20260904T185718` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159852/20260904T185707` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159865/20260904T185743` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159869/20260904T185720` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159870/20260904T185724` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159915/20260904T185617` | 6 | 0.2 MiB | .json×6 | meta.json … response_004.json | - |
| `tx/sz159949/20260904T185641` | 5 | 0.1 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz159985/20260904T185733` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz159992/20260904T185653` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159996/20260904T185808` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz159998/20260904T185803` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz300058/20260904T012431` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300189/20260904T012807` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300274/20260904T012411` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300274/20260904T012922` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300274/20260904T013152` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300285/20260904T012354` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300308/20260904T012251` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300394/20260904T012302` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300395/20260904T012718` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300454/20260904T012748` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300475/20260904T012435` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300476/20260904T012326` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300489/20260904T012543` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300502/20260904T012255` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300548/20260904T012553` | 5 | 0.2 MiB | .json×5 | meta.json … response_003.json | - |
| `tx/sz300570/20260904T012527` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300604/20260904T012438` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300620/20260904T012511` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300666/20260904T012514` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300672/20260904T012824` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300684/20260904T012745` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300684/20260904T012931` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300750/20260904T012344` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300750/20260904T012918` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300757/20260904T012517` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300759/20260904T012529` | 4 | 0.1 MiB | .json×4 | meta.json … response_002.json | - |
| `tx/sz300857/20260904T012427` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz300903/20260904T012706` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301018/20260904T012803` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301165/20260904T012610` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301171/20260904T012644` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301217/20260904T012440` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301308/20260904T012418` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301396/20260904T012602` | 3 | 0.1 MiB | .json×3 | meta.json … response_001.json | - |
| `tx/sz301511/20260904T012540` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sz301526/20260904T012421` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |
| `tx/sz301536/20260904T012829` | 2 | 0.0 MiB | .json×2 | meta.json … response_000.json | - |

### user_csv_1m

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `user_csv_1m/20260913-2` | 1 | 0.0 MiB | .json×1 | patches.json | - |
| `user_csv_1m/20260913-3` | 2 | 0.0 MiB | .json×1, .csv×1 | patches.json … sh.600623_2015-10-08_f5.csv | - |
| `user_csv_1m/20260913-4` | 4 | 0.0 MiB | .json×3, .csv×1 | patches.json … validation.json | - |

### user_dataset

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `user_dataset/2026-09-03/上证` | 3 | 835.0 MiB | .zip×3 | 不复权.zip … 后复权.zip | - |
| `user_dataset/2026-09-03/深证` | 3 | 1,196.7 MiB | .zip×3 | 不复权.zip … 后复权.zip | - |

### user_minute_1m

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `user_minute_1m/20260913-143215` | 1 | 0.0 MiB | .json×1 | transfer-manifest.json | - |
| `user_minute_1m/20260913-143215/2015` | 244 | 2,447.4 MiB | .parquet×244 | 20150105.parquet … 20151231.parquet | - |
| `user_minute_1m/20260913-143215/2016` | 244 | 2,633.1 MiB | .parquet×244 | 20160104.parquet … 20161230.parquet | - |
| `user_minute_1m/20260913-143215/2017` | 244 | 2,868.8 MiB | .parquet×244 | 20170103.parquet … 20171229.parquet | - |
| `user_minute_1m/20260913-143215/2018` | 243 | 3,003.6 MiB | .parquet×243 | 20180102.parquet … 20181228.parquet | - |
| `user_minute_1m/20260913-143215/2019` | 244 | 3,236.8 MiB | .parquet×244 | 20190102.parquet … 20191231.parquet | - |
| `user_minute_1m/20260913-2020-2024` | 1 | 0.0 MiB | .json×1 | transfer-manifest.json | - |
| `user_minute_1m/20260913-2020-2024/2020` | 243 | 3,673.4 MiB | .parquet×243 | 20200102.parquet … 20201231.parquet | - |
| `user_minute_1m/20260913-2020-2024/2021` | 243 | 4,218.0 MiB | .parquet×243 | 20210104.parquet … 20211231.parquet | - |
| `user_minute_1m/20260913-2020-2024/2022` | 242 | 4,642.3 MiB | .parquet×242 | 20220104.parquet … 20221230.parquet | - |
| `user_minute_1m/20260913-2020-2024/2023` | 242 | 4,797.7 MiB | .parquet×242 | 20230103.parquet … 20231229.parquet | - |
| `user_minute_1m/20260913-2020-2024/2024` | 242 | 5,008.8 MiB | .parquet×242 | 20240102.parquet … 20241231.parquet | - |

### xiaodefa

| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |
|---|---:|---:|---|---|---|
| `xiaodefa` | 2 | 3.1 MiB | .log×1, .json×1 | bulk.log … skipped-datasets.json | - |
| `xiaodefa/20260913-1` | 6 | 0.1 MiB | .json×6 | 002442.SZ_2016-03-01_response.json … 688165.SH_2021-11-01_response.json | - |
| `xiaodefa/20260914-300114-status` | 1 | 0.0 MiB | .json×1 | daily_20160503.json | - |
| `xiaodefa/20260914-minute-interface-probe` | 1 | 0.0 MiB | .json×1 | 600452.SH_2016-06-01_response.json | - |
| `xiaodefa/adj_factor/20260913-bulk1` | 3,089 | 321.6 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/block_trade/20260913-bulk1` | 3,089 | 70.8 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/bse_mapping/20260913-bulk1` | 2 | 0.0 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/cb_basic/20260913-bulk1` | 2 | 0.4 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/ccass_hold/20260913-bulk1` | 1,385 | 180.9 MiB | .csv×1384, .json×1 | chunk_20201111.csv … manifest.json | 20201111..20260911 (1384) |
| `xiaodefa/ci_daily/20260913-bulk1` | 2,758 | 111.7 MiB | .csv×2757, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20250508 (2757) |
| `xiaodefa/cn_cpi/20260913-bulk1` | 152 | 0.0 MiB | .csv×151, .json×1 | chunk_201401.csv … manifest.json | - |
| `xiaodefa/cn_m/20260913-bulk1` | 152 | 0.0 MiB | .csv×151, .json×1 | chunk_201401.csv … manifest.json | - |
| `xiaodefa/cn_pmi/20260913-bulk1` | 153 | 0.2 MiB | .csv×152, .json×1 | chunk_201401.csv … manifest.json | - |
| `xiaodefa/cn_ppi/20260913-bulk1` | 152 | 0.1 MiB | .csv×151, .json×1 | chunk_201401.csv … manifest.json | - |
| `xiaodefa/cn_schedule/20260913-bulk1` | 10 | 0.0 MiB | .csv×9, .json×1 | chunk_202601.csv … manifest.json | - |
| `xiaodefa/cyq_perf/20260913-bulk1` | 2,112 | 572.2 MiB | .csv×2111, .json×1 | chunk_20180102.csv … manifest.json | 20180102..20260911 (2111) |
| `xiaodefa/daily_info/20260913-bulk1` | 3,089 | 5.8 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/dc_daily/20260913-bulk1` | 1,625 | 153.4 MiB | .csv×1624, .json×1 | chunk_20200102.csv … manifest.json | 20200102..20260911 (1624) |
| `xiaodefa/dc_index/20260913-bulk1` | 7 | 22.0 MiB | .csv×3, .truncated×3, .json×1 | chunk_idx_type-地域板块.csv … manifest.json | - |
| `xiaodefa/etf_basic/20260913-bulk1` | 2 | 0.8 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/etf_index/20260913-bulk1` | 2 | 0.1 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/fund_basic/20260913-bulk1` | 4 | 18.4 MiB | .csv×3, .json×1 | chunk_market-E.csv … manifest.json | - |
| `xiaodefa/fund_company/20260913-bulk1` | 2 | 0.1 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/ggt_daily/20260913-bulk1` | 2,702 | 0.5 MiB | .csv×2701, .json×1 | chunk_20141117.csv … manifest.json | 20141117..20260911 (2701) |
| `xiaodefa/hk_hold/20260913-bulk1` | 2,285 | 293.9 MiB | .csv×2284, .json×1 | chunk_20170103.csv … manifest.json | 20170103..20260911 (2284) |
| `xiaodefa/hm_detail/20260913-bulk1` | 990 | 27.8 MiB | .csv×989, .json×1 | chunk_20220816.csv … manifest.json | 20220816..20260911 (989) |
| `xiaodefa/hs_const/20260913-bulk1` | 1 | 0.0 MiB | .json×1 | manifest.json | - |
| `xiaodefa/idx_factor_pro/20260913-bulk1` | 3,089 | 5,973.4 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/index_basic/20260913-bulk1` | 2 | 2.1 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/index_classify/20260913-bulk1` | 3 | 0.0 MiB | .csv×2, .json×1 | chunk_src-SW2014.csv … manifest.json | - |
| `xiaodefa/index_member_all/20260913-bulk1` | 5 | 1.2 MiB | .csv×2, .truncated×2, .json×1 | chunk_is_new-N.csv … manifest.json | - |
| `xiaodefa/limit_list_d/20260913-bulk1` | 1,625 | 21.5 MiB | .csv×1624, .json×1 | chunk_20200102.csv … manifest.json | 20200102..20260911 (1624) |
| `xiaodefa/minute-repairs-20260913-3` | 1 | 0.0 MiB | .json×1 | patches.json | - |
| `xiaodefa/minute-repairs-20260913-4` | 1 | 0.0 MiB | .json×1 | patches.json | - |
| `xiaodefa/minute-repairs-20260913-5` | 1 | 0.0 MiB | .json×1 | patches.json | - |
| `xiaodefa/minute-repairs-20260913-6` | 1 | 0.0 MiB | .json×1 | patches.json | - |
| `xiaodefa/minute-repairs-20260914-1` | 20 | 0.3 MiB | .csv×17, .json×3 | patches.json … sz.300420_2019-09-02_f5.csv | - |
| `xiaodefa/minute-repairs-20260914-2` | 3 | 0.1 MiB | .json×2, .csv×1 | patches.json … sz.002442_2016-03-01_reviewed_1m.json | - |
| `xiaodefa/minute-repairs-20260914-3` | 7 | 0.2 MiB | .json×4, .csv×3 | patches.json … sz.300461_2017-03-01_raw.json | - |
| `xiaodefa/moneyflow/20260913-bulk1` | 3,089 | 1,553.0 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/namechange/20260913-bulk1` | 2 | 1.5 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/repairs-20260913-1` | 8 | 0.0 MiB | .csv×7, .json×1 | baostock_sh_603178_2022-02-07_f5.csv … patches.json | - |
| `xiaodefa/repairs-20260913-2` | 2 | 0.0 MiB | .json×1, .csv×1 | patches.json … sz.300420_2019-09-02_f5.csv | - |
| `xiaodefa/sf_month/20260913-bulk1` | 152 | 0.0 MiB | .csv×151, .json×1 | chunk_201401.csv … manifest.json | - |
| `xiaodefa/st/20260913-bulk1` | 2 | 0.6 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/stk_auction_c/20260913-bulk1` | 3,089 | 836.9 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/stk_auction_o/20260913-bulk1` | 3,089 | 758.2 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/stk_limit/20260913-bulk1` | 3,089 | 438.7 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/stk_nineturn/20260913-bulk1` | 3,089 | 990.9 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/stk_surv/20260913-bulk1` | 1,168 | 79.1 MiB | .csv×1167, .json×1 | chunk_20210805.csv … manifest.json | 20210805..20260911 (1167) |
| `xiaodefa/stock_basic/20260913-bulk1` | 3 | 0.6 MiB | .csv×2, .json×1 | chunk_list_status-D.csv … manifest.json | - |
| `xiaodefa/stock_company/20260913-bulk1` | 2 | 9.6 MiB | .csv×1, .json×1 | chunk_p0.csv … manifest.json | - |
| `xiaodefa/stock_hsgt/20260913-bulk1` | 1 | 0.0 MiB | .json×1 | manifest.json | - |
| `xiaodefa/stock_st/20260913-bulk1` | 2 | 4.7 MiB | .csv×1, .json×1 | chunk_start_date-20140101_end_date-20260913.csv … manifest.json | - |
| `xiaodefa/suspend_d/20260913-bulk1` | 3,089 | 8.9 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/sw_daily/20260913-bulk1` | 3,087 | 173.4 MiB | .csv×3086, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3086) |
| `xiaodefa/sz_daily_info/20260913-bulk1` | 3,083 | 4.2 MiB | .csv×3082, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3082) |
| `xiaodefa/tdx_index/20260913-bulk1` | 7 | 11.7 MiB | .csv×2, .truncated×2, .truncated2×2, .json×1 | chunk_idx_type-概念板块.csv … manifest.json | - |
| `xiaodefa/ths_daily/20260913-bulk1` | 3,089 | 291.1 MiB | .csv×3088, .json×1 | chunk_20140102.csv … manifest.json | 20140102..20260911 (3088) |
| `xiaodefa/ths_index/20260913-bulk1` | 8 | 0.1 MiB | .csv×7, .json×1 | chunk_type-BB.csv … manifest.json | - |
| `xiaodefa/top10_floatholders/20260913-bulk1` | 3,050 | 149.2 MiB | .csv×3049, .json×1 | chunk_000001.SZ.csv … manifest.json | - |
| `xiaodefa/top10_holders/20260913-bulk1` | 5,894 | 327.6 MiB | .csv×5893, .json×1 | chunk_000001.SZ.csv … manifest.json | - |
| `xiaodefa/trade_cal/20260913-bulk1` | 4 | 0.4 MiB | .csv×3, .json×1 | chunk_exchange-CFFEX_start_date-20140101_end_date-20261231.csv … manifest.json | - |
