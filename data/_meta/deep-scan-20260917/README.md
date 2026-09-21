# raw 深扫补充台账 (deep-scan-20260917)

- 生成时间: 2026-09-18T00:16:02
- 范围: data/raw/{xiaodefa, tushare(除 20260917-r1 三批次), bigquant, em_fin, ths, tx, user_dataset, user_minute_1m(仅顶层清点)}
- 冻结边界: 2025-01-01 起冻结; 所有 >2024-12-31 的数据行均只报告、未删除、未修改 data/raw。
- data/raw 只读; 本目录仅新增, 不改动 data/_meta 既有文件。

## 汇总表

| 来源 | 数据集 | 批次 | 状态 | 文件数 | 行数 | 日期列 | 范围 | >2024-12-31 行 | 重复行 | blocker | warning | info | 单位结论 |
|---|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|
| bigquant | intraday-t0-20260914 | intraday-t0-20260914 | completed(per-file fallback) | 15 | 239,540 | date | 20210805 … 20241231 | 0 | - | 0 | 1 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/manifest | no_tabular_data | 6 | - | - | - … - | 0 | - | 0 | 1 | 2 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2010 | completed | 242 | 108,955,859 | file_date | 20100104 … 20101231 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2011 | completed | 244 | 129,144,911 | file_date | 20110104 … 20111230 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2012 | completed | 243 | 141,164,545 | file_date | 20120104 … 20121231 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2013 | completed | 238 | 141,375,902 | file_date | 20130104 … 20131231 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2014 | completed | 245 | 149,165,745 | file_date | 20140102 … 20141231 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2015 | completed(sampled 6/2607 files) | 2607 | - | sampled_file_date | 20150105 … 20151231 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2016 | completed(sampled 6/2834 files) | 2834 | - | sampled_file_date | 20160104 … 20161230 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2018 | completed(sampled 6/3370 files) | 3370 | - | sampled_file_date | 20180102 … 20181228 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2019 | completed(sampled 6/3572 files) | 3572 | - | sampled_file_date | 20190102 … 20191231 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2025 | completed | 243 | - | file_date | 20250102 … 20251231 | 0 | - | 1 | 0 | 0 | - |
| bigquant | minute-bulk-20260915-1 | minute-bulk-20260915-1/years/2026 | completed | 63 | - | file_date | 20260105 … 20260410 | 0 | - | 1 | 0 | 0 | - |
| bigquant | minute-check-20260914-1 | minute-check-20260914-1 | completed | 78 | 153,758 | date | 20150105 … 20240201 | 0 | - | 0 | 0 | 0 | - |
| bigquant | minute-repairs-20260914-1 | minute-repairs-20260914-1 | completed | 4 | 144 | time | 20160601 … 20190902 | 0 | - | 1 | 0 | 0 | - |
| em_fin | sh600030 | sh600030/20260904T013245 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600110 | sh600110/20260904T013306 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600150 | sh600150/20260904T013254 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600172 | sh600172/20260904T013249 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600176 | sh600176/20260904T013210 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600183 | sh600183/20260904T013210 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600186 | sh600186/20260904T013239 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600276 | sh600276/20260904T013230 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600397 | sh600397/20260904T013259 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600487 | sh600487/20260904T013208 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600519 | sh600519/20260904T013230 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600519 | sh600519/20260904T013638 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600584 | sh600584/20260904T013213 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600664 | sh600664/20260904T013237 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600869 | sh600869/20260904T013239 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600900 | sh600900/20260904T013251 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600988 | sh600988/20260904T013242 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh600989 | sh600989/20260904T013307 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601138 | sh601138/20260904T013215 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601179 | sh601179/20260904T080501 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601179 | sh601179/20260904T080803 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601208 | sh601208/20260904T013235 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601212 | sh601212/20260904T013539 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601318 | sh601318/20260904T013236 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601398 | sh601398/20260904T013245 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601718 | sh601718/20260904T212449 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601869 | sh601869/20260904T013221 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh601899 | sh601899/20260904T013212 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603083 | sh603083/20260904T013227 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603186 | sh603186/20260904T013227 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603228 | sh603228/20260904T013233 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603256 | sh603256/20260904T013246 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603259 | sh603259/20260904T013211 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603538 | sh603538/20260904T013304 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603618 | sh603618/20260904T013250 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603629 | sh603629/20260904T013223 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603799 | sh603799/20260904T013253 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603893 | sh603893/20260904T013250 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603986 | sh603986/20260904T013207 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603987 | sh603987/20260904T212438 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh603993 | sh603993/20260904T013229 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688008 | sh688008/20260904T013214 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688012 | sh688012/20260904T013216 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688017 | sh688017/20260904T013247 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688041 | sh688041/20260904T013219 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688048 | sh688048/20260904T013538 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688072 | sh688072/20260904T013229 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688110 | sh688110/20260904T013300 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688143 | sh688143/20260904T013246 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688146 | sh688146/20260904T013228 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688167 | sh688167/20260904T013243 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688183 | sh688183/20260904T013259 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688195 | sh688195/20260904T013256 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688205 | sh688205/20260904T013307 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688256 | sh688256/20260904T013209 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688300 | sh688300/20260904T013247 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688313 | sh688313/20260904T013233 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688347 | sh688347/20260904T013226 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688361 | sh688361/20260904T013238 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688498 | sh688498/20260904T013218 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688521 | sh688521/20260904T013235 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688525 | sh688525/20260904T013218 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688627 | sh688627/20260904T013252 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688702 | sh688702/20260904T013243 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688766 | sh688766/20260904T013217 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sh688981 | sh688981/20260904T013222 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000100 | sz000100/20260904T013255 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000338 | sz000338/20260904T013253 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000506 | sz000506/20260904T013256 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000636 | sz000636/20260904T013212 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000657 | sz000657/20260904T013217 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000703 | sz000703/20260904T013259 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000811 | sz000811/20260904T013303 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz000988 | sz000988/20260904T013226 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz001309 | sz001309/20260904T013216 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002008 | sz002008/20260904T013228 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002080 | sz002080/20260904T013244 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002081 | sz002081/20260904T013303 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002131 | sz002131/20260904T013249 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002384 | sz002384/20260904T013209 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002407 | sz002407/20260904T013220 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002428 | sz002428/20260904T013213 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002437 | sz002437/20260904T013244 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002536 | sz002536/20260904T013256 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002558 | sz002558/20260904T013305 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002580 | sz002580/20260904T013540 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002594 | sz002594/20260904T013539 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002716 | sz002716/20260904T013241 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002821 | sz002821/20260904T013257 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002837 | sz002837/20260904T013251 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002851 | sz002851/20260904T013232 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz002916 | sz002916/20260904T013240 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300058 | sz300058/20260904T013224 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300189 | sz300189/20260904T013302 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300274 | sz300274/20260904T013219 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300285 | sz300285/20260904T013215 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300308 | sz300308/20260904T013207 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300394 | sz300394/20260904T013208 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300395 | sz300395/20260904T013254 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300454 | sz300454/20260904T013258 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300475 | sz300475/20260904T013224 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300476 | sz300476/20260904T013211 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300489 | sz300489/20260904T013237 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300502 | sz300502/20260904T013207 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300548 | sz300548/20260904T013238 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300570 | sz300570/20260904T013234 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300604 | sz300604/20260904T013225 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300620 | sz300620/20260904T013231 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300666 | sz300666/20260904T013231 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300672 | sz300672/20260904T013305 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300684 | sz300684/20260904T013257 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300750 | sz300750/20260904T013214 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300757 | sz300757/20260904T013232 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300759 | sz300759/20260904T013234 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300857 | sz300857/20260904T013223 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz300903 | sz300903/20260904T013252 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301018 | sz301018/20260904T013301 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301165 | sz301165/20260904T013242 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301171 | sz301171/20260904T013248 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301217 | sz301217/20260904T013225 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301308 | sz301308/20260904T013220 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301396 | sz301396/20260904T013240 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301511 | sz301511/20260904T013236 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301526 | sz301526/20260904T013222 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| em_fin | sz301536 | sz301536/20260904T013306 | completed | 2 | 9 | record_date | 20240630 … 20260630 | 6 | - | 1 | 0 | 0 | - |
| ths | sh510050 | sh510050/20260903T040924 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh510050 | sh510050/20260903T042255 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh510300 | sh510300/20260903T040925 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | close_510300=中位 3.802 元, 符合沪深300ETF量级(2-8元); confidence=high |
| ths | sh510300 | sh510300/20260903T042252 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | close_510300=中位 3.802 元, 符合沪深300ETF量级(2-8元); confidence=high |
| ths | sh510500 | sh510500/20260903T040925 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh510500 | sh510500/20260903T042253 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh510880 | sh510880/20260903T040930 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh510880 | sh510880/20260903T042259 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512010 | sh512010/20260903T040927 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512010 | sh512010/20260903T042259 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512100 | sh512100/20260903T040926 | completed | 2 | 1208 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512100 | sh512100/20260903T042253 | completed | 2 | 1208 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512170 | sh512170/20260903T042258 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512200 | sh512200/20260903T042308 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512400 | sh512400/20260903T040928 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512400 | sh512400/20260903T042255 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512480 | sh512480/20260903T040927 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512690 | sh512690/20260903T040927 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512690 | sh512690/20260903T042301 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512710 | sh512710/20260903T042304 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512800 | sh512800/20260903T040928 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512800 | sh512800/20260903T042256 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512880 | sh512880/20260903T040926 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512880 | sh512880/20260903T042254 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512890 | sh512890/20260903T042256 | completed | 2 | 1208 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh512980 | sh512980/20260903T042303 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh513100 | sh513100/20260903T040930 | completed | 2 | 1208 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515030 | sh515030/20260903T042307 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515170 | sh515170/20260903T042309 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515210 | sh515210/20260903T042308 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515220 | sh515220/20260903T042257 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515790 | sh515790/20260903T040929 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515790 | sh515790/20260903T042305 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515800 | sh515800/20260903T042308 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh515880 | sh515880/20260903T042252 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh516150 | sh516150/20260903T042306 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh516160 | sh516160/20260903T040929 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh516510 | sh516510/20260903T042305 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh516970 | sh516970/20260903T042311 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh517520 | sh517520/20260903T042255 | completed | 2 | 690 | record_date | 20231101 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh518880 | sh518880/20260903T040930 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh518880 | sh518880/20260903T042251 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh560080 | sh560080/20260903T042310 | completed | 2 | 944 | record_date | 20221017 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh560170 | sh560170/20260903T042312 | completed | 2 | 768 | record_date | 20230706 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh560280 | sh560280/20260903T042307 | completed | 2 | 692 | record_date | 20231030 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh561360 | sh561360/20260903T042309 | completed | 2 | 691 | record_date | 20231031 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh562800 | sh562800/20260903T042303 | completed | 2 | 1196 | record_date | 20210927 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh563300 | sh563300/20260903T042257 | completed | 2 | 718 | record_date | 20230914 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh588000 | sh588000/20260903T042251 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sh588170 | sh588170/20260903T042250 | completed | 2 | 344 | record_date | 20250408 … 20260902 | 344 | - | 1 | 0 | 0 | - |
| ths | sh588220 | sh588220/20260903T042258 | completed | 2 | 717 | record_date | 20230915 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159301 | sz159301/20260903T042312 | completed | 2 | 515 | record_date | 20240722 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159530 | sz159530/20260903T042258 | completed | 2 | 635 | record_date | 20240118 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159565 | sz159565/20260903T042311 | completed | 2 | 614 | record_date | 20240226 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159611 | sz159611/20260903T042301 | completed | 2 | 1128 | record_date | 20220107 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159732 | sz159732/20260903T042302 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159745 | sz159745/20260903T042311 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159755 | sz159755/20260903T042302 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159766 | sz159766/20260903T042306 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159819 | sz159819/20260903T042300 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159852 | sz159852/20260903T042259 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159865 | sz159865/20260903T042304 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159869 | sz159869/20260903T042300 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159870 | sz159870/20260903T042301 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159915 | sz159915/20260903T040926 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159915 | sz159915/20260903T042252 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159949 | sz159949/20260903T042254 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159985 | sz159985/20260903T042303 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159992 | sz159992/20260903T042256 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159996 | sz159996/20260903T042310 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| ths | sz159998 | sz159998/20260903T042309 | completed | 2 | 1209 | record_date | 20210906 … 20260902 | 405 | - | 1 | 0 | 0 | - |
| tushare | balancesheet | balancesheet/20260909-r3 | completed | 5900 | 408,781 | f_ann_date | 19920223 … 20260831 | 49,329 | 245,466 | 1 | 1 | 2 | - |
| tushare | balancesheet | balancesheet/20260910-r1 | completed | 5 | 241 | f_ann_date | 20090409 … 20260828 | 23 | 138 | 1 | 0 | 1 | - |
| tushare | cashflow | cashflow/20260909-r3 | completed | 5900 | 396,385 | f_ann_date | 20060118 … 20260901 | 65,923 | 173,133 | 1 | 1 | 2 | - |
| tushare | cashflow | cashflow/20260910-r1 | completed | 9 | 388 | f_ann_date | 20061020 … 20260828 | 83 | 200 | 1 | 0 | 1 | - |
| tushare | daily_basic | daily_basic/20260909-r1 | completed | 1867 | 8,850,300 | trade_date | 20190102 … 20260909 | 2,232,372 | 0 | 1 | 0 | 1 | close=元, 与 baostock 不复权收盘一致; total_mv=万元 (total_mv*1e4 ≈ close*total_share); confidence=high |
| tushare | daily_basic | daily_basic/20260913-r2 | completed | 977 | 2,774,097 | trade_date | 20150105 … 20181228 | 0 | 0 | 0 | 0 | 1 | close=元, 与 baostock 不复权收盘一致; total_mv=万元 (total_mv*1e4 ≈ close*total_share); confidence=high |
| tushare | disclosure_date | disclosure_date/20260909-r1 | completed | 32 | 148,313 | pre_date | 20190122 … 20260831 | 38,318 | 0 | 1 | 0 | 1 | - |
| tushare | dividend | dividend/20260909-r3 | completed | 2110 | 35,940 | ex_date | 20180103 … 20260909 | 9510 | 1840 | 1 | 1 | 2 | - |
| tushare | dividend | dividend/20260913-r2 | completed | 733 | 7626 | imp_ann_date | 20141225 … 20171223 | 0 | 472 | 0 | 1 | 2 | - |
| tushare | events | events | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| tushare | express | express/20260909-r1 | completed | 32 | 8488 | end_date | 20181231 … 20260630 | 174 | 0 | 1 | 0 | 2 | - |
| tushare | fina_indicator | fina_indicator/20260909-r3 | completed | 5900 | 458,575 | ann_date | 19920429 … 20260901 | 52,067 | 388,958 | 1 | 1 | 2 | - |
| tushare | fina_indicator | fina_indicator/20260910-r1 | completed | 4 | 143 | ann_date | 20121020 … 20260829 | 19 | 114 | 1 | 1 | 0 | - |
| tushare | forecast | forecast/20260909-r1 | completed | 98 | 50,406 | ann_date | 20180903 … 20260904 | 10,327 | 0 | 1 | 0 | 1 | - |
| tushare | fund_basic | fund_basic/20260909-r1 | completed | 3 | 35,691 | found_date | 19980327 … 20260909 | 6501 | 5890 | 1 | 1 | 0 | - |
| tushare | income | income/20260909-r3 | completed | 5900 | 421,679 | f_ann_date | 19950105 … 20260901 | 52,216 | 149,415 | 1 | 1 | 2 | - |
| tushare | income | income/20260910-r1 | completed | 4 | 233 | f_ann_date | 19950228 … 20260831 | 19 | 52 | 1 | 0 | 1 | - |
| tushare | index_daily | index_daily/20260917-r1 | completed | 6 | 12,155 | trade_date | 20150105 … 20241231 | 0 | 0 | 0 | 0 | 0 | - |
| tushare | index_member_all | index_member_all/20260909-r1 | completed(per-file fallback) | 5 | 6413 | in_date | 19891101 … 20260903 | 334 | 0 | 1 | 1 | 0 | - |
| tushare | margin_detail | margin_detail/20260909-r1 | completed | 1867 | 5,474,653 | trade_date | 20190102 … 20260908 | 1,730,402 | 0 | 1 | 0 | 2 | rzye=元量级: 茅台融资余额数十亿元 ≈ 1e10; confidence=medium |
| tushare | r3 | r3 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| tushare | repurchase | repurchase/20260909-r3 | completed | 130 | 61,718 | ann_date | 20160104 … 20260909 | 12,625 | 5195 | 1 | 1 | 1 | - |
| tushare | share_float | share_float/20260909-r3 | completed | 130 | 5,661,143 | float_date | 20151124 … 20340120 | 1,622,054 | 5,654,928 | 1 | 1 | 1 | - |
| tushare | statements | statements | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| tushare | stk_holdertrade | stk_holdertrade/20260909-r3 | completed | 130 | 149,108 | ann_date | 20160101 … 20260909 | 21,356 | 73,884 | 1 | 1 | 1 | - |
| tushare | stock_basic | stock_basic/20260909-r3 | completed | 4 | 5899 | list_date | 19901201 … 20260909 | 227 | 0 | 1 | 0 | 1 | - |
| tushare | sw_index_daily | sw_index_daily/20260909-r1 | completed | 32 | 55,155 | date | 20190102 … 20260828 | 12,462 | - | 1 | 0 | 1 | - |
| tushare | sw_index_daily | sw_index_daily/20260909-r2 | completed | 32 | 55,155 | date | 20190102 … 20260828 | 12,462 | - | 1 | 0 | 0 | - |
| tushare | sw_index_daily | sw_index_daily/20260909-r3 | completed | 33 | 148,404 | date | 19991230 … 20260908 | 12,679 | - | 1 | 0 | 0 | - |
| tushare | sw_index_daily | sw_index_daily/20260909-r4-verify | completed | 32 | 143,096 | - | - … - | 0 | - | 0 | 0 | 0 | - |
| tushare | sw_index_daily_l2 | sw_index_daily_l2/20260909-r1 | completed | 132 | 419,551 | - | - … - | 0 | - | 0 | 0 | 0 | - |
| tushare | top_inst | top_inst/20260909-r3 | completed | 1867 | 1,785,667 | trade_date | 20190102 … 20260909 | 341,394 | 1,785,665 | 1 | 1 | 1 | - |
| tushare | top_list | top_list/20260909-r1 | completed | 1867 | 141,985 | trade_date | 20190102 … 20260908 | 31,823 | 46,186 | 1 | 1 | 2 | - |
| tushare | trade_cal | trade_cal/20260909-r1 | completed | 4 | 4748 | cal_date | 20140101 … 20261231 | 730 | 0 | 0 | 1 | 0 | - |
| tx | sh510050 | sh510050/20260904T185651 | completed | 8 | 5240 | record_date | 20050223 … 20260904 | 407 | 6 | 1 | 2 | 0 | - |
| tx | sh510300 | sh510300/20260904T185625 | completed | 6 | 3475 | record_date | 20120528 … 20260904 | 407 | 4 | 1 | 2 | 0 | close_510300=中位 3.32 元, 符合沪深300ETF量级(2-8元); confidence=high |
| tx | sh510500 | sh510500/20260904T185633 | completed | 6 | 3278 | record_date | 20130315 … 20260904 | 407 | 4 | 1 | 2 | 0 | - |
| tx | sh510880 | sh510880/20260904T185713 | completed | 7 | 4775 | record_date | 20070118 … 20260904 | 407 | 5 | 1 | 2 | 0 | - |
| tx | sh512010 | sh512010/20260904T185716 | completed | 5 | 3131 | record_date | 20131028 … 20260904 | 407 | 3 | 1 | 2 | 0 | - |
| tx | sh512100 | sh512100/20260904T185628 | completed | 4 | 2392 | record_date | 20161104 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512170 | sh512170/20260904T185705 | completed | 4 | 1756 | record_date | 20190617 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512200 | sh512200/20260904T185756 | completed | 4 | 2173 | record_date | 20170925 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512400 | sh512400/20260904T185643 | completed | 4 | 2189 | record_date | 20170901 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512690 | sh512690/20260904T185723 | completed | 4 | 1785 | record_date | 20190506 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512710 | sh512710/20260904T185741 | completed | 4 | 1706 | record_date | 20190826 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512800 | sh512800/20260904T185656 | completed | 4 | 2210 | record_date | 20170803 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512880 | sh512880/20260904T185637 | completed | 5 | 2451 | record_date | 20160808 … 20260904 | 407 | 3 | 1 | 2 | 0 | - |
| tx | sh512890 | sh512890/20260904T185659 | completed | 4 | 1852 | record_date | 20190118 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh512980 | sh512980/20260904T185736 | completed | 4 | 2095 | record_date | 20180119 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh515030 | sh515030/20260904T185752 | completed | 3 | 1582 | record_date | 20200304 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh515170 | sh515170/20260904T185805 | completed | 3 | 1370 | record_date | 20210113 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh515210 | sh515210/20260904T185758 | completed | 3 | 1584 | record_date | 20200302 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh515220 | sh515220/20260904T185701 | completed | 3 | 1584 | record_date | 20200302 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh515790 | sh515790/20260904T185745 | completed | 3 | 1387 | record_date | 20201218 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh515800 | sh515800/20260904T185801 | completed | 4 | 1633 | record_date | 20191216 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh515880 | sh515880/20260904T185620 | completed | 4 | 1698 | record_date | 20190906 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh516150 | sh516150/20260904T185748 | completed | 3 | 1330 | record_date | 20210317 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh516510 | sh516510/20260904T185747 | completed | 3 | 1316 | record_date | 20210407 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh516970 | sh516970/20260904T185814 | completed | 3 | 1257 | record_date | 20210705 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh517520 | sh517520/20260904T185651 | completed | 2 | 692 | record_date | 20231101 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sh518880 | sh518880/20260904T185611 | completed | 5 | 3191 | record_date | 20130729 … 20260904 | 407 | 3 | 1 | 2 | 0 | - |
| tx | sh560080 | sh560080/20260904T185810 | completed | 3 | 947 | record_date | 20221017 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh560170 | sh560170/20260904T185815 | completed | 2 | 770 | record_date | 20230706 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sh560280 | sh560280/20260904T185753 | completed | 2 | 694 | record_date | 20231030 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sh561360 | sh561360/20260904T185806 | completed | 2 | 693 | record_date | 20231031 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sh562800 | sh562800/20260904T185738 | completed | 3 | 1199 | record_date | 20210927 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh563300 | sh563300/20260904T185659 | completed | 2 | 720 | record_date | 20230914 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sh588000 | sh588000/20260904T185607 | completed | 3 | 1411 | record_date | 20201116 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sh588170 | sh588170/20260904T080651 | completed | 2 | 345 | record_date | 20250408 … 20260903 | 345 | - | 1 | 0 | 0 | - |
| tx | sh588170 | sh588170/20260904T213728 | completed | 2 | 346 | record_date | 20250408 … 20260904 | 346 | - | 1 | 0 | 0 | - |
| tx | sh588220 | sh588220/20260904T185702 | completed | 2 | 719 | record_date | 20230915 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sh600030 | sh600030/20260904T012630 | completed | 5 | 3200 | record_date | 20130620 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600110 | sh600110/20260904T012833 | completed | 5 | 3200 | record_date | 20120515 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600150 | sh600150/20260904T012722 | completed | 5 | 3200 | record_date | 20121206 … 20260903 | 402 | 3 | 1 | 2 | 0 | - |
| tx | sh600172 | sh600172/20260904T012648 | completed | 5 | 3200 | record_date | 20130328 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600176 | sh600176/20260904T012315 | completed | 5 | 3200 | record_date | 20130613 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600183 | sh600183/20260904T012319 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600183 | sh600183/20260904T012916 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600183 | sh600183/20260904T013145 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600186 | sh600186/20260904T012556 | completed | 5 | 3200 | record_date | 20121221 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600276 | sh600276/20260904T012504 | completed | 5 | 3200 | record_date | 20130712 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600397 | sh600397/20260904T012755 | completed | 5 | 3200 | record_date | 20130416 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600487 | sh600487/20260904T012306 | completed | 5 | 3200 | record_date | 20130121 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600519 | sh600519/20260904T012508 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600519 | sh600519/20260904T012925 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600519 | sh600519/20260904T013141 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600519 | sh600519/20260904T013637 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600584 | sh600584/20260904T012341 | completed | 5 | 3200 | record_date | 20120807 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600664 | sh600664/20260904T012547 | completed | 5 | 3200 | record_date | 20121213 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600869 | sh600869/20260904T012600 | completed | 5 | 3200 | record_date | 20130304 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600900 | sh600900/20260904T012701 | completed | 5 | 3200 | record_date | 20130110 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh600988 | sh600988/20260904T012614 | completed | 5 | 3200 | record_date | 20120903 … 20260903 | 404 | 3 | 1 | 2 | 0 | - |
| tx | sh600989 | sh600989/20260904T012835 | completed | 4 | 1777 | record_date | 20190516 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh601138 | sh601138/20260904T012350 | completed | 4 | 2003 | record_date | 20180608 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh601179 | sh601179/20260904T080459 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh601179 | sh601179/20260904T080802 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh601208 | sh601208/20260904T012535 | completed | 5 | 3200 | record_date | 20130708 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh601212 | sh601212/20260904T012801 | completed | 4 | 2282 | record_date | 20170215 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh601318 | sh601318/20260904T012539 | completed | 5 | 3200 | record_date | 20130712 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh601398 | sh601398/20260904T012634 | completed | 5 | 3200 | record_date | 20130715 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh601718 | sh601718/20260904T091546 | completed | 5 | 3200 | record_date | 20130628 … 20260903 | 405 | 3 | 1 | 2 | 0 | - |
| tx | sh601718 | sh601718/20260904T212447 | completed | 5 | 3201 | record_date | 20130628 … 20260904 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh601869 | sh601869/20260904T012421 | completed | 4 | 1974 | record_date | 20180720 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh601899 | sh601899/20260904T012334 | completed | 5 | 3200 | record_date | 20130529 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh603083 | sh603083/20260904T012447 | completed | 4 | 2143 | record_date | 20171110 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603186 | sh603186/20260904T012449 | completed | 4 | 2351 | record_date | 20170103 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603228 | sh603228/20260904T012522 | completed | 4 | 2348 | record_date | 20170106 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603256 | sh603256/20260904T012637 | completed | 4 | 1732 | record_date | 20190719 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603259 | sh603259/20260904T012322 | completed | 4 | 2026 | record_date | 20180508 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603538 | sh603538/20260904T012821 | completed | 4 | 2217 | record_date | 20170407 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603618 | sh603618/20260904T012656 | completed | 5 | 2784 | record_date | 20150217 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh603629 | sh603629/20260904T012426 | completed | 4 | 1869 | record_date | 20181224 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603799 | sh603799/20260904T012714 | completed | 5 | 2788 | record_date | 20150129 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh603893 | sh603893/20260904T012657 | completed | 3 | 1599 | record_date | 20200207 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh603986 | sh603986/20260904T012258 | completed | 4 | 2235 | record_date | 20160818 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603987 | sh603987/20260904T091542 | completed | 4 | 2381 | record_date | 20161121 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh603987 | sh603987/20260904T212436 | completed | 4 | 2382 | record_date | 20161121 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sh603993 | sh603993/20260904T012459 | completed | 5 | 3200 | record_date | 20130613 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sh688008 | sh688008/20260904T012347 | completed | 4 | 1731 | record_date | 20190722 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh688012 | sh688012/20260904T012356 | completed | 4 | 1722 | record_date | 20190722 … 20260903 | 397 | 2 | 1 | 2 | 0 | - |
| tx | sh688017 | sh688017/20260904T012643 | completed | 3 | 1460 | record_date | 20200828 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688041 | sh688041/20260904T012412 | completed | 3 | 976 | record_date | 20220812 … 20260903 | 396 | 1 | 1 | 2 | 0 | - |
| tx | sh688048 | sh688048/20260904T012616 | completed | 3 | 1075 | record_date | 20220401 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688072 | sh688072/20260904T012501 | completed | 3 | 1054 | record_date | 20220420 … 20260903 | 396 | 1 | 1 | 2 | 0 | - |
| tx | sh688110 | sh688110/20260904T012759 | completed | 3 | 1146 | record_date | 20211210 … 20260903 | 403 | 1 | 1 | 2 | 0 | - |
| tx | sh688143 | sh688143/20260904T012638 | completed | 3 | 894 | record_date | 20221212 … 20260903 | 403 | 1 | 1 | 2 | 0 | - |
| tx | sh688146 | sh688146/20260904T012451 | completed | 3 | 816 | record_date | 20230421 … 20260903 | 403 | 1 | 1 | 2 | 0 | - |
| tx | sh688167 | sh688167/20260904T012618 | completed | 3 | 1139 | record_date | 20211224 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688183 | sh688183/20260904T012757 | completed | 3 | 1343 | record_date | 20210225 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688195 | sh688195/20260904T012735 | completed | 3 | 1312 | record_date | 20210326 … 20260903 | 396 | 1 | 1 | 2 | 0 | - |
| tx | sh688205 | sh688205/20260904T012837 | completed | 3 | 989 | record_date | 20220809 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688256 | sh688256/20260904T012308 | completed | 3 | 1489 | record_date | 20200720 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688300 | sh688300/20260904T012641 | completed | 4 | 1653 | record_date | 20191115 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sh688313 | sh688313/20260904T012524 | completed | 3 | 1463 | record_date | 20200812 … 20260903 | 397 | 1 | 1 | 2 | 0 | - |
| tx | sh688347 | sh688347/20260904T012444 | completed | 2 | 737 | record_date | 20230807 … 20260903 | 396 | - | 1 | 0 | 0 | - |
| tx | sh688361 | sh688361/20260904T012549 | completed | 3 | 802 | record_date | 20230519 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688498 | sh688498/20260904T012405 | completed | 3 | 899 | record_date | 20221221 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688521 | sh688521/20260904T012531 | completed | 3 | 1458 | record_date | 20200818 … 20260903 | 396 | 1 | 1 | 2 | 0 | - |
| tx | sh688525 | sh688525/20260904T012407 | completed | 3 | 892 | record_date | 20221230 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sh688627 | sh688627/20260904T012707 | completed | 2 | 761 | record_date | 20230718 … 20260903 | 406 | - | 1 | 0 | 0 | - |
| tx | sh688702 | sh688702/20260904T012617 | completed | 2 | 719 | record_date | 20230914 … 20260903 | 406 | - | 1 | 0 | 0 | - |
| tx | sh688766 | sh688766/20260904T012400 | completed | 3 | 1211 | record_date | 20210823 … 20260903 | 396 | 1 | 1 | 2 | 0 | - |
| tx | sh688981 | sh688981/20260904T012423 | completed | 3 | 1485 | record_date | 20200716 … 20260903 | 400 | 1 | 1 | 2 | 0 | - |
| tx | sz000100 | sz000100/20260904T012730 | completed | 5 | 3200 | record_date | 20120918 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000338 | sz000338/20260904T012710 | completed | 5 | 3200 | record_date | 20130710 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000338 | sz000338/20260904T012928 | completed | 5 | 3200 | record_date | 20130710 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000338 | sz000338/20260904T013148 | completed | 5 | 3200 | record_date | 20130710 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000506 | sz000506/20260904T012739 | completed | 5 | 3200 | record_date | 20120118 … 20260903 | 405 | 3 | 1 | 2 | 0 | - |
| tx | sz000636 | sz000636/20260904T012330 | completed | 5 | 3200 | record_date | 20121105 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000657 | sz000657/20260904T012403 | completed | 5 | 3200 | record_date | 20091222 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000703 | sz000703/20260904T012751 | completed | 5 | 3200 | record_date | 20130327 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000811 | sz000811/20260904T012815 | completed | 5 | 3200 | record_date | 20130219 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz000988 | sz000988/20260904T012443 | completed | 5 | 3200 | record_date | 20130710 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz001309 | sz001309/20260904T012358 | completed | 3 | 1016 | record_date | 20220701 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz002008 | sz002008/20260904T012455 | completed | 5 | 3200 | record_date | 20130620 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002080 | sz002080/20260904T012622 | completed | 5 | 3200 | record_date | 20121231 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002081 | sz002081/20260904T012811 | completed | 5 | 3200 | record_date | 20130503 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002131 | sz002131/20260904T012652 | completed | 5 | 3200 | record_date | 20120716 … 20260903 | 403 | 3 | 1 | 2 | 0 | - |
| tx | sz002384 | sz002384/20260904T012311 | completed | 5 | 3200 | record_date | 20120905 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002407 | sz002407/20260904T012416 | completed | 5 | 3200 | record_date | 20130228 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002428 | sz002428/20260904T012337 | completed | 5 | 3200 | record_date | 20130703 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002437 | sz002437/20260904T012626 | completed | 5 | 3200 | record_date | 20120608 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002536 | sz002536/20260904T012733 | completed | 5 | 3200 | record_date | 20130626 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002558 | sz002558/20260904T012828 | completed | 5 | 3200 | record_date | 20111226 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002580 | sz002580/20260904T012819 | completed | 5 | 3200 | record_date | 20121113 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002594 | sz002594/20260904T012726 | completed | 5 | 3200 | record_date | 20130701 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002716 | sz002716/20260904T012609 | completed | 5 | 2876 | record_date | 20140128 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz002821 | sz002821/20260904T012742 | completed | 4 | 2382 | record_date | 20161118 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz002837 | sz002837/20260904T012704 | completed | 4 | 2277 | record_date | 20161229 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz002851 | sz002851/20260904T012519 | completed | 4 | 2232 | record_date | 20170306 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz002916 | sz002916/20260904T012605 | completed | 4 | 2118 | record_date | 20171213 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz159301 | sz159301/20260904T185816 | completed | 2 | 517 | record_date | 20240722 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sz159530 | sz159530/20260904T185702 | completed | 2 | 637 | record_date | 20240118 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sz159565 | sz159565/20260904T185814 | completed | 2 | 616 | record_date | 20240226 … 20260904 | 407 | - | 1 | 0 | 0 | - |
| tx | sz159611 | sz159611/20260904T185726 | completed | 3 | 1131 | record_date | 20220107 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159732 | sz159732/20260904T185728 | completed | 3 | 1222 | record_date | 20210823 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159745 | sz159745/20260904T185812 | completed | 3 | 1268 | record_date | 20210618 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159755 | sz159755/20260904T185730 | completed | 3 | 1264 | record_date | 20210624 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159766 | sz159766/20260904T185750 | completed | 3 | 1243 | record_date | 20210723 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159819 | sz159819/20260904T185718 | completed | 3 | 1443 | record_date | 20200923 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159852 | sz159852/20260904T185707 | completed | 3 | 1351 | record_date | 20210209 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159865 | sz159865/20260904T185743 | completed | 3 | 1337 | record_date | 20210308 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159869 | sz159869/20260904T185720 | completed | 3 | 1338 | record_date | 20210305 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159870 | sz159870/20260904T185724 | completed | 3 | 1340 | record_date | 20210303 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159915 | sz159915/20260904T185617 | completed | 6 | 3583 | record_date | 20111209 … 20260904 | 407 | 4 | 1 | 2 | 0 | - |
| tx | sz159949 | sz159949/20260904T185641 | completed | 5 | 2462 | record_date | 20160722 … 20260904 | 407 | 3 | 1 | 2 | 0 | - |
| tx | sz159985 | sz159985/20260904T185733 | completed | 4 | 1640 | record_date | 20191205 … 20260904 | 407 | 2 | 1 | 2 | 0 | - |
| tx | sz159992 | sz159992/20260904T185653 | completed | 3 | 1556 | record_date | 20200410 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159996 | sz159996/20260904T185808 | completed | 3 | 1574 | record_date | 20200316 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz159998 | sz159998/20260904T185803 | completed | 3 | 1555 | record_date | 20200413 … 20260904 | 407 | 1 | 1 | 2 | 0 | - |
| tx | sz300058 | sz300058/20260904T012431 | completed | 5 | 3200 | record_date | 20130121 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300189 | sz300189/20260904T012807 | completed | 5 | 3200 | record_date | 20120604 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300274 | sz300274/20260904T012411 | completed | 5 | 3200 | record_date | 20130613 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300274 | sz300274/20260904T012922 | completed | 5 | 3200 | record_date | 20130613 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300274 | sz300274/20260904T013152 | completed | 5 | 3200 | record_date | 20130613 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300285 | sz300285/20260904T012354 | completed | 5 | 3200 | record_date | 20121218 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300308 | sz300308/20260904T012251 | completed | 5 | 3200 | record_date | 20121029 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300394 | sz300394/20260904T012302 | completed | 5 | 2797 | record_date | 20150217 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300395 | sz300395/20260904T012718 | completed | 5 | 2916 | record_date | 20140910 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300454 | sz300454/20260904T012748 | completed | 4 | 2020 | record_date | 20180516 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300475 | sz300475/20260904T012435 | completed | 5 | 2706 | record_date | 20150610 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300476 | sz300476/20260904T012326 | completed | 5 | 2729 | record_date | 20150611 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300489 | sz300489/20260904T012543 | completed | 5 | 2711 | record_date | 20150701 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300502 | sz300502/20260904T012255 | completed | 5 | 2556 | record_date | 20160303 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300548 | sz300548/20260904T012553 | completed | 5 | 2406 | record_date | 20161012 … 20260903 | 406 | 3 | 1 | 2 | 0 | - |
| tx | sz300570 | sz300570/20260904T012527 | completed | 4 | 2370 | record_date | 20161206 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300604 | sz300604/20260904T012438 | completed | 4 | 2273 | record_date | 20170417 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300620 | sz300620/20260904T012511 | completed | 4 | 2298 | record_date | 20170310 … 20260903 | 396 | 2 | 1 | 2 | 0 | - |
| tx | sz300666 | sz300666/20260904T012514 | completed | 4 | 2223 | record_date | 20170615 … 20260903 | 401 | 2 | 1 | 2 | 0 | - |
| tx | sz300672 | sz300672/20260904T012824 | completed | 4 | 2202 | record_date | 20170712 … 20260903 | 396 | 2 | 1 | 2 | 0 | - |
| tx | sz300684 | sz300684/20260904T012745 | completed | 4 | 2110 | record_date | 20171227 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300684 | sz300684/20260904T012931 | completed | 4 | 2110 | record_date | 20171227 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300750 | sz300750/20260904T012344 | completed | 4 | 2002 | record_date | 20180611 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300750 | sz300750/20260904T012918 | completed | 4 | 2002 | record_date | 20180611 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300757 | sz300757/20260904T012517 | completed | 4 | 1840 | record_date | 20190108 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300759 | sz300759/20260904T012529 | completed | 4 | 1846 | record_date | 20190128 … 20260903 | 406 | 2 | 1 | 2 | 0 | - |
| tx | sz300857 | sz300857/20260904T012427 | completed | 3 | 1484 | record_date | 20200727 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz300903 | sz300903/20260904T012706 | completed | 3 | 1417 | record_date | 20201105 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz301018 | sz301018/20260904T012803 | completed | 3 | 1254 | record_date | 20210707 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz301165 | sz301165/20260904T012610 | completed | 3 | 921 | record_date | 20221121 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz301171 | sz301171/20260904T012644 | completed | 3 | 978 | record_date | 20220819 … 20260903 | 403 | 1 | 1 | 2 | 0 | - |
| tx | sz301217 | sz301217/20260904T012440 | completed | 3 | 1116 | record_date | 20220127 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz301308 | sz301308/20260904T012418 | completed | 3 | 991 | record_date | 20220805 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz301396 | sz301396/20260904T012602 | completed | 3 | 927 | record_date | 20221111 … 20260903 | 406 | 1 | 1 | 2 | 0 | - |
| tx | sz301511 | sz301511/20260904T012540 | completed | 2 | 739 | record_date | 20230817 … 20260903 | 406 | - | 1 | 0 | 0 | - |
| tx | sz301526 | sz301526/20260904T012421 | completed | 2 | 652 | record_date | 20231226 … 20260903 | 406 | - | 1 | 0 | 0 | - |
| tx | sz301536 | sz301536/20260904T012829 | completed | 2 | 592 | record_date | 20240328 … 20260903 | 406 | - | 1 | 0 | 0 | - |
| user_dataset | 2026-09-03 | 2026-09-03/上证 | completed | 3 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_dataset | 2026-09-03 | 2026-09-03/深证 | completed | 3 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-143215 | 20260913-143215/2015 | completed | 244 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-143215 | 20260913-143215/2016 | completed | 244 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-143215 | 20260913-143215/2017 | completed | 244 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-143215 | 20260913-143215/2018 | completed | 243 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-143215 | 20260913-143215/2019 | completed | 244 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-2020-2024 | 20260913-2020-2024/2020 | completed | 243 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-2020-2024 | 20260913-2020-2024/2021 | completed | 243 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-2020-2024 | 20260913-2020-2024/2022 | completed | 242 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-2020-2024 | 20260913-2020-2024/2023 | completed | 242 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| user_minute_1m | 20260913-2020-2024 | 20260913-2020-2024/2024 | completed | 242 | - | - | - … - | 0 | - | 0 | 0 | 0 | - |
| xiaodefa | 20260913-1 | 20260913-1 | no_tabular_data | 6 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | 20260914-300114-status | 20260914-300114-status | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | 20260914-minute-interface-probe | 20260914-minute-interface-probe | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | adj_factor | adj_factor/20260913-bulk1 | completed | 3089 | 12,862,104 | trade_date | 20140102 … 20260911 | 2,254,223 | 0 | 1 | 1 | 1 | - |
| xiaodefa | block_trade | block_trade/20260913-bulk1 | completed | 3089 | 629,797 | trade_date | 20140102 … 20260911 | 66,597 | 127,449 | 1 | 1 | 1 | - |
| xiaodefa | bse_mapping | bse_mapping/20260913-bulk1 | completed | 2 | 248 | list_date | 20200727 … 20240408 | 0 | - | 0 | 0 | 0 | - |
| xiaodefa | cb_basic | cb_basic/20260913-bulk1 | completed | 2 | 1164 | conv_end_date | 19951231 … 20320909 | 885 | 0 | 1 | 0 | 0 | - |
| xiaodefa | ccass_hold | ccass_hold/20260913-bulk1 | completed | 1385 | 3,781,826 | trade_date | 20201111 … 20260911 | 930,593 | 0 | 1 | 0 | 1 | - |
| xiaodefa | ci_daily | ci_daily/20260913-bulk1 | completed | 2758 | 1,220,122 | trade_date | 20140102 … 20250508 | 35,397 | 0 | 1 | 0 | 1 | - |
| xiaodefa | cn_cpi | cn_cpi/20260913-bulk1 | completed | 152 | 151 | month | 201401 … 202607 | 19 | - | 1 | 0 | 1 | - |
| xiaodefa | cn_m | cn_m/20260913-bulk1 | completed | 152 | 151 | month | 201401 … 202607 | 19 | - | 1 | 0 | 1 | - |
| xiaodefa | cn_pmi | cn_pmi/20260913-bulk1 | completed | 153 | 152 | month | 201401 … 202608 | 20 | - | 1 | 0 | 1 | - |
| xiaodefa | cn_ppi | cn_ppi/20260913-bulk1 | completed | 152 | 151 | month | 201401 … 202607 | 19 | - | 1 | 0 | 1 | - |
| xiaodefa | cn_schedule | cn_schedule/20260913-bulk1 | completed | 10 | 131 | publish_date | 20260104 … 20260930 | 131 | - | 1 | 0 | 0 | - |
| xiaodefa | cyq_perf | cyq_perf/20260913-bulk1 | completed(per-file fallback) | 2112 | 9,475,775 | trade_date | 20180102 … 20260911 | 2,243,438 | 0 | 1 | 1 | 0 | - |
| xiaodefa | daily_info | daily_info/20260913-bulk1 | completed | 3089 | 61,441 | trade_date | 20140102 … 20260911 | 4904 | 61,441 | 1 | 1 | 1 | - |
| xiaodefa | dc_daily | dc_daily/20260913-bulk1 | completed | 1625 | 1,470,419 | trade_date | 20200102 … 20260911 | 411,871 | 34,246 | 1 | 1 | 1 | - |
| xiaodefa | dc_index | dc_index/20260913-bulk1 | completed | 7 | 195,781 | trade_date | 20250530 … 20260911 | 195,781 | 0 | 1 | 0 | 0 | - |
| xiaodefa | etf_basic | etf_basic/20260913-bulk1 | completed | 2 | 3414 | list_date | 20050223 … 20260902 | 1040 | 0 | 1 | 0 | 0 | - |
| xiaodefa | etf_index | etf_index/20260913-bulk1 | completed | 2 | 560 | pub_date | 18960526 … 20250627 | 10 | 0 | 1 | 0 | 0 | - |
| xiaodefa | fund_basic | fund_basic/20260913-bulk1 | completed | 4 | 65,956 | found_date | 19980327 … 20260911 | 11,818 | 65,956 | 1 | 1 | 0 | - |
| xiaodefa | fund_company | fund_company/20260913-bulk1 | completed | 2 | 204 | end_date | 20091229 … 20091229 | 0 | - | 0 | 0 | 0 | - |
| xiaodefa | ggt_daily | ggt_daily/20260913-bulk1 | completed | 2702 | 2701 | trade_date | 20141117 … 20260911 | 402 | 0 | 1 | 0 | 1 | - |
| xiaodefa | hk_hold | hk_hold/20260913-bulk1 | completed | 2285 | 5,650,165 | trade_date | 20170103 … 20260911 | 364,971 | 480 | 1 | 1 | 1 | - |
| xiaodefa | hm_detail | hm_detail/20260913-bulk1 | completed | 990 | 231,162 | trade_date | 20220816 … 20260911 | 107,634 | 226,369 | 1 | 1 | 1 | - |
| xiaodefa | hs_const | hs_const/20260913-bulk1 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | idx_factor_pro | idx_factor_pro/20260913-bulk1 | completed | 3089 | 7,963,931 | trade_date | 20140102 … 20260911 | 1,404,637 | 0 | 1 | 0 | 1 | - |
| xiaodefa | index_basic | index_basic/20260913-bulk1 | completed | 2 | 20,752 | list_date | 19221231 … 20260921 | 1707 | 0 | 1 | 0 | 0 | - |
| xiaodefa | index_classify | index_classify/20260913-bulk1 | completed | 3 | 870 | - | - … - | 0 | - | 0 | 0 | 0 | - |
| xiaodefa | index_member_all | index_member_all/20260913-bulk1 | completed | 5 | 7982 | in_date | 19840509 … 20260828 | 331 | 3725 | 1 | 1 | 0 | - |
| xiaodefa | limit_list_d | limit_list_d/20260913-bulk1 | completed | 1625 | 163,686 | trade_date | 20200102 … 20260911 | 45,796 | 0 | 1 | 0 | 1 | - |
| xiaodefa | minute-repairs-20260913-3 | minute-repairs-20260913-3 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | minute-repairs-20260913-4 | minute-repairs-20260913-4 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | minute-repairs-20260913-5 | minute-repairs-20260913-5 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | minute-repairs-20260913-6 | minute-repairs-20260913-6 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | minute-repairs-20260914-1 | minute-repairs-20260914-1 | completed | 20 | 816 | time | 20150701 … 20190902 | 0 | - | 1 | 0 | 0 | - |
| xiaodefa | minute-repairs-20260914-2 | minute-repairs-20260914-2 | completed | 3 | 48 | time | 20160301 … 20160301 | 0 | - | 1 | 0 | 0 | - |
| xiaodefa | minute-repairs-20260914-3 | minute-repairs-20260914-3 | completed | 7 | 144 | time | 20160601 … 20170301 | 0 | - | 1 | 0 | 0 | - |
| xiaodefa | moneyflow | moneyflow/20260913-bulk1 | completed(per-file fallback) | 3089 | 11,947,770 | trade_date | 20140102 … 20260911 | 2,135,000 | 0 | 1 | 1 | 0 | amount_like_cols=万元量级(单票主力净额数千至数万元档); confidence=medium |
| xiaodefa | namechange | namechange/20260913-bulk1 | completed | 2 | 34,749 | start_date | 19901201 … 20260911 | 1297 | 29,672 | 1 | 1 | 0 | - |
| xiaodefa | pledge_detail | pledge_detail/20260913-bulk1 | no_tabular_data | 0 | - | - | - … - | 0 | - | 0 | 1 | 0 | - |
| xiaodefa | repairs-20260913-1 | repairs-20260913-1 | completed | 8 | 336 | time | 20211101 … 20240201 | 0 | - | 1 | 0 | 0 | - |
| xiaodefa | repairs-20260913-2 | repairs-20260913-2 | completed | 2 | 48 | time | 20190902 … 20190902 | 0 | - | 1 | 0 | 0 | - |
| xiaodefa | sf_month | sf_month/20260913-bulk1 | completed | 152 | 151 | inc_month | 10224.27 … 9665.13 | 96 | 0 | 1 | 0 | 1 | - |
| xiaodefa | st | st/20260913-bulk1 | completed | 2 | 1000 | pub_date | 20230428 … 20260912 | 615 | 763 | 1 | 1 | 0 | - |
| xiaodefa | stk_auction_c | stk_auction_c/20260913-bulk1 | completed | 3089 | 12,836,978 | trade_date | 20140102 … 20260911 | 2,310,928 | 0 | 1 | 0 | 1 | - |
| xiaodefa | stk_auction_o | stk_auction_o/20260913-bulk1 | completed | 3089 | 12,480,358 | trade_date | 20140102 … 20260911 | 2,246,039 | 0 | 1 | 0 | 1 | - |
| xiaodefa | stk_limit | stk_limit/20260913-bulk1 | completed(per-file fallback) | 3089 | 14,832,091 | trade_date | 20140102 … 20260911 | 3,016,608 | 0 | 1 | 1 | 0 | limit_price=元; 与前收盘 ±10% 关系成立; confidence=high |
| xiaodefa | stk_nineturn | stk_nineturn/20260913-bulk1 | completed | 3089 | 11,880,008 | trade_date | 20140102 … 20260911 | 2,244,771 | 0 | 1 | 0 | 1 | - |
| xiaodefa | stk_surv | stk_surv/20260913-bulk1 | completed | 1168 | 385,967 | surv_date | 20210805 … 20260911 | 116,712 | 385,579 | 1 | 1 | 1 | - |
| xiaodefa | stock_basic | stock_basic/20260913-bulk1 | completed | 3 | 5904 | list_date | 19700101 … 20260911 | 225 | 0 | 1 | 0 | 0 | - |
| xiaodefa | stock_company | stock_company/20260913-bulk1 | completed | 2 | 5000 | setup_date | 19551001 … 20201208 | 0 | 0 | 0 | 0 | 0 | - |
| xiaodefa | stock_hsgt | stock_hsgt/20260913-bulk1 | no_tabular_data | 1 | - | - | - … - | 0 | - | 0 | 0 | 1 | - |
| xiaodefa | stock_st | stock_st/20260913-bulk1 | completed | 2 | 101,000 | trade_date | 20240516 … 20260913 | 79,691 | 0 | 1 | 0 | 0 | - |
| xiaodefa | suspend_d | suspend_d/20260913-bulk1 | completed | 3089 | 386,303 | trade_date | 20140102 … 20260911 | 6775 | 154 | 1 | 1 | 1 | - |
| xiaodefa | sw_daily | sw_daily/20260913-bulk1 | completed(per-file fallback) | 3087 | 1,411,239 | trade_date | 20140102 … 20260911 | 178,852 | 0 | 1 | 1 | 0 | - |
| xiaodefa | sz_daily_info | sz_daily_info/20260913-bulk1 | completed | 3083 | 45,276 | trade_date | 20140102 … 20260911 | 5742 | 45,274 | 1 | 1 | 1 | - |
| xiaodefa | tdx_index | tdx_index/20260913-bulk1 | completed | 7 | 148,507 | trade_date | 20250328 … 20260911 | 148,507 | 264 | 1 | 1 | 0 | - |
| xiaodefa | ths_daily | ths_daily/20260913-bulk1 | completed | 3089 | 2,902,613 | trade_date | 20140102 … 20260911 | 637,628 | 0 | 1 | 0 | 1 | - |
| xiaodefa | ths_index | ths_index/20260913-bulk1 | completed | 8 | 2722 | list_date | 19910715 … 20260731 | 453 | 0 | 1 | 0 | 0 | - |
| xiaodefa | top10_floatholders | top10_floatholders/20260913-bulk1 | completed | 3050 | 1,458,617 | ann_date | 20050418 … 20260831 | 190,464 | - | 1 | 0 | 1 | - |
| xiaodefa | top10_holders | top10_holders/20260913-bulk1 | completed | 5894 | 3,283,981 | ann_date | 19901210 … 20260831 | 418,166 | - | 1 | 0 | 1 | - |
| xiaodefa | top_list | top_list/20260913-bulk1 | no_tabular_data | 0 | - | - | - … - | 0 | - | 0 | 1 | 0 | - |
| xiaodefa | trade_cal | trade_cal/20260913-bulk1 | completed | 4 | 14,124 | cal_date | 20140101 … 20261231 | 2190 | 0 | 0 | 1 | 0 | - |

## 问题分级汇总 (blocker=465, warning=390, info=70)

### blocker

- `bigquant/minute-bulk-20260915-1` [frozen_window_data_present] 2025 年目录全部 243 个文件属于冻结区(2025/2026), 按文件名登记未读取内容
- `bigquant/minute-bulk-20260915-1` [frozen_window_data_present] 2026 年目录全部 63 个文件属于冻结区(2025/2026), 按文件名登记未读取内容
- `bigquant/minute-repairs-20260914-1` [manifest_missing] 批次目录内无 manifest.json/sha256/meta 清单
- `em_fin/sh600030` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600110` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600150` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600172` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600176` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600183` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600186` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600276` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600397` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600487` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600519` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600519` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600584` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600664` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600869` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600900` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600988` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh600989` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601138` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601179` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601179` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601208` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601212` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601318` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601398` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601718` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601869` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh601899` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603083` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603186` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603228` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603256` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603259` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603538` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603618` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603629` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603799` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603893` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603986` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603987` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh603993` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688008` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688012` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688017` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688041` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688048` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688072` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688110` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688143` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688146` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688167` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688183` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688195` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688205` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688256` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688300` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688313` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688347` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688361` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688498` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688521` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688525` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688627` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688702` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688766` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sh688981` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000100` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000338` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000506` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000636` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000657` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000703` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000811` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz000988` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz001309` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002008` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002080` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002081` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002131` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002384` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002407` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002428` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002437` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002536` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002558` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002580` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002594` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002716` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002821` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002837` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002851` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz002916` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300058` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300189` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300274` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300285` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300308` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300394` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300395` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300454` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300475` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300476` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300489` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300502` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300548` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300570` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300604` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300620` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300666` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300672` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300684` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300750` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300757` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300759` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300857` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz300903` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301018` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301165` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301171` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301217` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301308` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301396` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301511` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301526` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `em_fin/sz301536` [frozen_window_rows] 6 个记录日期 > 2024-12-31 (max=20260630); 冻结边界: 只报告
- `ths/sh510050` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510050` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510300` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510300` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510500` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510500` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh510880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512010` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512010` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512100` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512100` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512170` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512200` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512400` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512400` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512480` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512690` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512690` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512710` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512800` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512800` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512890` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh512980` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh513100` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515030` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515170` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515210` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515220` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515790` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515790` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515800` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh515880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh516150` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh516160` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh516510` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh516970` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh517520` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh518880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh518880` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh560080` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh560170` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh560280` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh561360` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh562800` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh563300` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh588000` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh588170` [frozen_window_rows] 344 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sh588220` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159301` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159530` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159565` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159611` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159732` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159745` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159755` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159766` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159819` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159852` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159865` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159869` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159870` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159915` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159915` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159949` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159985` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159992` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159996` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `ths/sz159998` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260902); 冻结边界: 只报告
- `tushare/balancesheet` [frozen_window_rows] 日期列 f_ann_date 有 49329 行 > 2024-12-31 (max=20260831); 冻结边界审查: 只报告不删除
- `tushare/balancesheet` [frozen_window_rows] 日期列 ann_date 有 23 行 > 2024-12-31 (max=20260828); 冻结边界审查: 只报告不删除
- `tushare/cashflow` [frozen_window_rows] 日期列 f_ann_date 有 65923 行 > 2024-12-31 (max=20260901); 冻结边界审查: 只报告不删除
- `tushare/cashflow` [frozen_window_rows] 日期列 ann_date 有 83 行 > 2024-12-31 (max=20260828); 冻结边界审查: 只报告不删除
- `tushare/daily_basic` [frozen_window_rows] 日期列 trade_date 有 2232372 行 > 2024-12-31 (max=20260909); 冻结边界审查: 只报告不删除
- `tushare/disclosure_date` [frozen_window_rows] 日期列 pre_date 有 38318 行 > 2024-12-31 (max=20260831); 冻结边界审查: 只报告不删除
- `tushare/dividend` [frozen_window_rows] 日期列 record_date 有 9510 行 > 2024-12-31 (max=20260908); 冻结边界审查: 只报告不删除
- `tushare/express` [frozen_window_rows] 日期列 ann_date 有 174 行 > 2024-12-31 (max=20260825); 冻结边界审查: 只报告不删除
- `tushare/fina_indicator` [frozen_window_rows] 日期列 ann_date 有 52067 行 > 2024-12-31 (max=20260901); 冻结边界审查: 只报告不删除
- `tushare/fina_indicator` [frozen_window_rows] 日期列 ann_date 有 19 行 > 2024-12-31 (max=20260829); 冻结边界审查: 只报告不删除
- `tushare/forecast` [frozen_window_rows] 日期列 ann_date 有 10327 行 > 2024-12-31 (max=20260904); 冻结边界审查: 只报告不删除
- `tushare/fund_basic` [frozen_window_rows] 日期列 found_date 有 6501 行 > 2024-12-31 (max=20260909); 冻结边界审查: 只报告不删除
- `tushare/income` [frozen_window_rows] 日期列 f_ann_date 有 52216 行 > 2024-12-31 (max=20260901); 冻结边界审查: 只报告不删除
- `tushare/income` [frozen_window_rows] 日期列 ann_date 有 19 行 > 2024-12-31 (max=20260831); 冻结边界审查: 只报告不删除
- `tushare/index_member_all` [frozen_window_rows] 日期列 in_date 有 334 行 > 2024-12-31
- `tushare/margin_detail` [frozen_window_rows] 日期列 trade_date 有 1730402 行 > 2024-12-31 (max=20260908); 冻结边界审查: 只报告不删除
- `tushare/repurchase` [frozen_window_rows] 日期列 ann_date 有 12625 行 > 2024-12-31 (max=20260909); 冻结边界审查: 只报告不删除
- `tushare/share_float` [frozen_window_rows] 日期列 float_date 有 1622054 行 > 2024-12-31 (max=20340120); 冻结边界审查: 只报告不删除
- `tushare/stk_holdertrade` [frozen_window_rows] 日期列 ann_date 有 21356 行 > 2024-12-31 (max=20260909); 冻结边界审查: 只报告不删除
- `tushare/stock_basic` [frozen_window_rows] 日期列 list_date 有 227 行 > 2024-12-31 (max=20260909); 冻结边界审查: 只报告不删除
- `tushare/sw_index_daily` [frozen_window_rows] 日期列 date 有 12462 行 > 2024-12-31 (max=20260828); 冻结边界审查: 只报告不删除
- `tushare/sw_index_daily` [frozen_window_rows] 日期列 date 有 12462 行 > 2024-12-31 (max=20260828); 冻结边界审查: 只报告不删除
- `tushare/sw_index_daily` [frozen_window_rows] 日期列 date 有 12679 行 > 2024-12-31 (max=20260908); 冻结边界审查: 只报告不删除
- `tushare/top_inst` [frozen_window_rows] 日期列 trade_date 有 341394 行 > 2024-12-31 (max=20260909); 冻结边界审查: 只报告不删除
- `tushare/top_list` [frozen_window_rows] 日期列 trade_date 有 31823 行 > 2024-12-31 (max=20260908); 冻结边界审查: 只报告不删除
- `tx/sh510050` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh510300` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh510500` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh510880` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512010` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512100` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512170` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512200` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512400` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512690` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512710` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512800` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512880` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512890` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh512980` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515030` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515170` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515210` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515220` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515790` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515800` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh515880` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh516150` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh516510` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh516970` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh517520` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh518880` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh560080` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh560170` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh560280` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh561360` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh562800` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh563300` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh588000` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh588170` [frozen_window_rows] 345 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh588170` [frozen_window_rows] 346 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh588220` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh600030` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600110` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600150` [frozen_window_rows] 402 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600172` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600176` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600183` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600183` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600183` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600186` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600276` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600397` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600487` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600519` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600519` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600519` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600519` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600584` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600664` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600869` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600900` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600988` [frozen_window_rows] 404 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh600989` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601138` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601179` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601179` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601208` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601212` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601318` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601398` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601718` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601718` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh601869` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh601899` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603083` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603186` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603228` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603256` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603259` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603538` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603618` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603629` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603799` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603893` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603986` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603987` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh603987` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sh603993` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688008` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688012` [frozen_window_rows] 397 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688017` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688041` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688048` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688072` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688110` [frozen_window_rows] 403 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688143` [frozen_window_rows] 403 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688146` [frozen_window_rows] 403 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688167` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688183` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688195` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688205` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688256` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688300` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688313` [frozen_window_rows] 397 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688347` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688361` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688498` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688521` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688525` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688627` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688702` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688766` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sh688981` [frozen_window_rows] 400 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000100` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000338` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000338` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000338` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000506` [frozen_window_rows] 405 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000636` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000657` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000703` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000811` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz000988` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz001309` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002008` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002080` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002081` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002131` [frozen_window_rows] 403 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002384` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002407` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002428` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002437` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002536` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002558` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002580` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002594` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002716` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002821` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002837` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002851` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz002916` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz159301` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159530` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159565` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159611` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159732` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159745` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159755` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159766` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159819` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159852` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159865` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159869` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159870` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159915` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159949` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159985` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159992` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159996` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz159998` [frozen_window_rows] 407 个记录日期 > 2024-12-31 (max=20260904); 冻结边界: 只报告
- `tx/sz300058` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300189` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300274` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300274` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300274` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300285` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300308` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300394` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300395` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300454` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300475` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300476` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300489` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300502` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300548` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300570` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300604` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300620` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300666` [frozen_window_rows] 401 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300672` [frozen_window_rows] 396 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- `tx/sz300684` [frozen_window_rows] 406 个记录日期 > 2024-12-31 (max=20260903); 冻结边界: 只报告
- …(更多略, 见各批次 JSON)

### warning

- `bigquant/intraday-t0-20260914` [bulk_scan_failed_perfile_fallback] ComputeError: schema lengths differ
- `bigquant/minute-bulk-20260915-1` [inventory_file_count_mismatch] 登记 2 个文件, 实际 6
- `tushare/balancesheet` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'report_type'] 重复 245466 行; 含 update_flag 后仍重复 2093 行
- `tushare/cashflow` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'report_type'] 重复 173133 行; 含 update_flag 后仍重复 1299 行
- `tushare/dividend` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'div_proc'] 重复: 920 个键 / 1840 行
- `tushare/dividend` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'div_proc'] 重复: 236 个键 / 472 行
- `tushare/fina_indicator` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'ann_date'] 重复: 194479 个键 / 388958 行
- `tushare/fina_indicator` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'ann_date'] 重复: 57 个键 / 114 行
- `tushare/fund_basic` [duplicate_primary_key_rows] 主键 ['ts_code'] 重复: 2945 个键 / 5890 行
- `tushare/income` [duplicate_primary_key_rows] 主键 ['ts_code', 'end_date', 'report_type'] 重复 149415 行; 含 update_flag 后仍重复 2759 行
- `tushare/index_member_all` [bulk_scan_failed_perfile_fallback] ComputeError: schema lengths differ
- `tushare/repurchase` [duplicate_primary_key_rows] 主键 ['ts_code', 'ann_date'] 重复: 2289 个键 / 5195 行
- `tushare/share_float` [duplicate_primary_key_rows] 主键 ['ts_code', 'ann_date', 'float_date'] 重复: 21560 个键 / 5654928 行
- `tushare/stk_holdertrade` [duplicate_primary_key_rows] 主键 ['ts_code', 'ann_date', 'holder_name'] 重复: 17435 个键 / 73884 行
- `tushare/top_inst` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date'] 重复: 116580 个键 / 1785665 行
- `tushare/top_list` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date'] 重复: 21714 个键 / 46186 行
- `tushare/trade_cal` [frozen_window_rows_reference_calendar] 日期列 cal_date 有 730 行 > 2024-12-31 (max=20261231); 冻结边界审查: 只报告不删除; 参考日历类数据, 2025+ 为日历定义而非行情观测
- `tx/sh510050` [meta_row_count_mismatch] meta n_rows=5234, 实际解析 5240 行, 其中跨页重复日期 6 行
- `tx/sh510050` [duplicate_kline_dates_across_pages] 跨页重复日期 6 行, 例: ['20061208', '20100325', '20130715', '20161025', '20200206', '20230522']
- `tx/sh510300` [meta_row_count_mismatch] meta n_rows=3471, 实际解析 3475 行, 其中跨页重复日期 4 行
- `tx/sh510300` [duplicate_kline_dates_across_pages] 跨页重复日期 4 行, 例: ['20130715', '20161025', '20200206', '20230522']
- `tx/sh510500` [meta_row_count_mismatch] meta n_rows=3274, 实际解析 3278 行, 其中跨页重复日期 4 行
- `tx/sh510500` [duplicate_kline_dates_across_pages] 跨页重复日期 4 行, 例: ['20130711', '20161025', '20200206', '20230522']
- `tx/sh510880` [meta_row_count_mismatch] meta n_rows=4770, 实际解析 4775 行, 其中跨页重复日期 5 行
- `tx/sh510880` [duplicate_kline_dates_across_pages] 跨页重复日期 5 行, 例: ['20100325', '20130715', '20161025', '20200206', '20230522']
- `tx/sh512010` [meta_row_count_mismatch] meta n_rows=3128, 实际解析 3131 行, 其中跨页重复日期 3 行
- `tx/sh512010` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161021', '20200205', '20230522']
- `tx/sh512100` [meta_row_count_mismatch] meta n_rows=2390, 实际解析 2392 行, 其中跨页重复日期 2 行
- `tx/sh512100` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200205', '20230522']
- `tx/sh512170` [meta_row_count_mismatch] meta n_rows=1754, 实际解析 1756 行, 其中跨页重复日期 2 行
- `tx/sh512170` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200205', '20230522']
- `tx/sh512200` [meta_row_count_mismatch] meta n_rows=2171, 实际解析 2173 行, 其中跨页重复日期 2 行
- `tx/sh512200` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh512400` [meta_row_count_mismatch] meta n_rows=2187, 实际解析 2189 行, 其中跨页重复日期 2 行
- `tx/sh512400` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh512690` [meta_row_count_mismatch] meta n_rows=1783, 实际解析 1785 行, 其中跨页重复日期 2 行
- `tx/sh512690` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200205', '20230522']
- `tx/sh512710` [meta_row_count_mismatch] meta n_rows=1704, 实际解析 1706 行, 其中跨页重复日期 2 行
- `tx/sh512710` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200205', '20230522']
- `tx/sh512800` [meta_row_count_mismatch] meta n_rows=2208, 实际解析 2210 行, 其中跨页重复日期 2 行
- `tx/sh512800` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh512880` [meta_row_count_mismatch] meta n_rows=2448, 实际解析 2451 行, 其中跨页重复日期 3 行
- `tx/sh512880` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161026', '20200207', '20230523']
- `tx/sh512890` [meta_row_count_mismatch] meta n_rows=1850, 实际解析 1852 行, 其中跨页重复日期 2 行
- `tx/sh512890` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200205', '20230522']
- `tx/sh512980` [meta_row_count_mismatch] meta n_rows=2093, 实际解析 2095 行, 其中跨页重复日期 2 行
- `tx/sh512980` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200207', '20230523']
- `tx/sh515030` [meta_row_count_mismatch] meta n_rows=1581, 实际解析 1582 行, 其中跨页重复日期 1 行
- `tx/sh515030` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh515170` [meta_row_count_mismatch] meta n_rows=1369, 实际解析 1370 行, 其中跨页重复日期 1 行
- `tx/sh515170` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh515210` [meta_row_count_mismatch] meta n_rows=1583, 实际解析 1584 行, 其中跨页重复日期 1 行
- `tx/sh515210` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh515220` [meta_row_count_mismatch] meta n_rows=1583, 实际解析 1584 行, 其中跨页重复日期 1 行
- `tx/sh515220` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh515790` [meta_row_count_mismatch] meta n_rows=1386, 实际解析 1387 行, 其中跨页重复日期 1 行
- `tx/sh515790` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh515800` [meta_row_count_mismatch] meta n_rows=1631, 实际解析 1633 行, 其中跨页重复日期 2 行
- `tx/sh515800` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh515880` [meta_row_count_mismatch] meta n_rows=1696, 实际解析 1698 行, 其中跨页重复日期 2 行
- `tx/sh515880` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh516150` [meta_row_count_mismatch] meta n_rows=1329, 实际解析 1330 行, 其中跨页重复日期 1 行
- `tx/sh516150` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh516510` [meta_row_count_mismatch] meta n_rows=1315, 实际解析 1316 行, 其中跨页重复日期 1 行
- `tx/sh516510` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh516970` [meta_row_count_mismatch] meta n_rows=1256, 实际解析 1257 行, 其中跨页重复日期 1 行
- `tx/sh516970` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh518880` [meta_row_count_mismatch] meta n_rows=3188, 实际解析 3191 行, 其中跨页重复日期 3 行
- `tx/sh518880` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh560080` [meta_row_count_mismatch] meta n_rows=946, 实际解析 947 行, 其中跨页重复日期 1 行
- `tx/sh560080` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh562800` [meta_row_count_mismatch] meta n_rows=1198, 实际解析 1199 行, 其中跨页重复日期 1 行
- `tx/sh562800` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sh588000` [meta_row_count_mismatch] meta n_rows=1410, 实际解析 1411 行, 其中跨页重复日期 1 行
- `tx/sh588000` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh600030` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600030` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160923', '20200121', '20230522']
- `tx/sh600110` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600110` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160630', '20200117', '20230522']
- `tx/sh600150` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600150` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160325', '20200108', '20230427']
- `tx/sh600172` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600172` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160927', '20200122', '20230515']
- `tx/sh600176` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600176` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160930', '20200115', '20230522']
- `tx/sh600183` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600183` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600183` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600183` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600183` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600183` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600186` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600186` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161019', '20200205', '20230522']
- `tx/sh600276` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600276` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600397` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600397` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161021', '20200206', '20230522']
- `tx/sh600487` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600487` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160920', '20200206', '20230522']
- `tx/sh600519` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600519` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600519` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600519` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600519` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600519` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600519` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600519` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh600584` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600584` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160922', '20200122', '20230515']
- `tx/sh600664` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600664` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160527', '20200206', '20230522']
- `tx/sh600869` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600869` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160929', '20200206', '20230522']
- `tx/sh600900` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600900` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161010', '20200114', '20230522']
- `tx/sh600988` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh600988` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161011', '20200204', '20230518']
- `tx/sh600989` [meta_row_count_mismatch] meta n_rows=1775, 实际解析 1777 行, 其中跨页重复日期 2 行
- `tx/sh600989` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh601138` [meta_row_count_mismatch] meta n_rows=2001, 实际解析 2003 行, 其中跨页重复日期 2 行
- `tx/sh601138` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh601179` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601179` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh601179` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601179` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh601208` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601208` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh601212` [meta_row_count_mismatch] meta n_rows=2280, 实际解析 2282 行, 其中跨页重复日期 2 行
- `tx/sh601212` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh601318` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601318` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh601398` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601398` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh601718` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601718` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161024', '20200205', '20230519']
- `tx/sh601718` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3201 行, 其中跨页重复日期 3 行
- `tx/sh601718` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161024', '20200205', '20230519']
- `tx/sh601869` [meta_row_count_mismatch] meta n_rows=1972, 实际解析 1974 行, 其中跨页重复日期 2 行
- `tx/sh601869` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh601899` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh601899` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161019', '20200206', '20230522']
- `tx/sh603083` [meta_row_count_mismatch] meta n_rows=2141, 实际解析 2143 行, 其中跨页重复日期 2 行
- `tx/sh603083` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603186` [meta_row_count_mismatch] meta n_rows=2349, 实际解析 2351 行, 其中跨页重复日期 2 行
- `tx/sh603186` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603228` [meta_row_count_mismatch] meta n_rows=2346, 实际解析 2348 行, 其中跨页重复日期 2 行
- `tx/sh603228` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603256` [meta_row_count_mismatch] meta n_rows=1730, 实际解析 1732 行, 其中跨页重复日期 2 行
- `tx/sh603256` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603259` [meta_row_count_mismatch] meta n_rows=2024, 实际解析 2026 行, 其中跨页重复日期 2 行
- `tx/sh603259` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603538` [meta_row_count_mismatch] meta n_rows=2215, 实际解析 2217 行, 其中跨页重复日期 2 行
- `tx/sh603538` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603618` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2784 行, 其中跨页重复日期 3 行
- `tx/sh603618` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh603629` [meta_row_count_mismatch] meta n_rows=1867, 实际解析 1869 行, 其中跨页重复日期 2 行
- `tx/sh603629` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603799` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2788 行, 其中跨页重复日期 3 行
- `tx/sh603799` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160930', '20200206', '20230522']
- `tx/sh603893` [meta_row_count_mismatch] meta n_rows=1598, 实际解析 1599 行, 其中跨页重复日期 1 行
- `tx/sh603893` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh603986` [meta_row_count_mismatch] meta n_rows=2233, 实际解析 2235 行, 其中跨页重复日期 2 行
- `tx/sh603986` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603987` [meta_row_count_mismatch] meta n_rows=2379, 实际解析 2381 行, 其中跨页重复日期 2 行
- `tx/sh603987` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603987` [meta_row_count_mismatch] meta n_rows=2380, 实际解析 2382 行, 其中跨页重复日期 2 行
- `tx/sh603987` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh603993` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sh603993` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sh688008` [meta_row_count_mismatch] meta n_rows=1729, 实际解析 1731 行, 其中跨页重复日期 2 行
- `tx/sh688008` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh688012` [meta_row_count_mismatch] meta n_rows=1720, 实际解析 1722 行, 其中跨页重复日期 2 行
- `tx/sh688012` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200116', '20230509']
- `tx/sh688017` [meta_row_count_mismatch] meta n_rows=1459, 实际解析 1460 行, 其中跨页重复日期 1 行
- `tx/sh688017` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688041` [meta_row_count_mismatch] meta n_rows=975, 实际解析 976 行, 其中跨页重复日期 1 行
- `tx/sh688041` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230508']
- `tx/sh688048` [meta_row_count_mismatch] meta n_rows=1074, 实际解析 1075 行, 其中跨页重复日期 1 行
- `tx/sh688048` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688072` [meta_row_count_mismatch] meta n_rows=1053, 实际解析 1054 行, 其中跨页重复日期 1 行
- `tx/sh688072` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230508']
- `tx/sh688110` [meta_row_count_mismatch] meta n_rows=1145, 实际解析 1146 行, 其中跨页重复日期 1 行
- `tx/sh688110` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230517']
- `tx/sh688143` [meta_row_count_mismatch] meta n_rows=893, 实际解析 894 行, 其中跨页重复日期 1 行
- `tx/sh688143` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230504']
- `tx/sh688146` [meta_row_count_mismatch] meta n_rows=815, 实际解析 816 行, 其中跨页重复日期 1 行
- `tx/sh688146` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230517']
- `tx/sh688167` [meta_row_count_mismatch] meta n_rows=1138, 实际解析 1139 行, 其中跨页重复日期 1 行
- `tx/sh688167` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688183` [meta_row_count_mismatch] meta n_rows=1342, 实际解析 1343 行, 其中跨页重复日期 1 行
- `tx/sh688183` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688195` [meta_row_count_mismatch] meta n_rows=1311, 实际解析 1312 行, 其中跨页重复日期 1 行
- `tx/sh688195` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230508']
- `tx/sh688205` [meta_row_count_mismatch] meta n_rows=988, 实际解析 989 行, 其中跨页重复日期 1 行
- `tx/sh688205` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688256` [meta_row_count_mismatch] meta n_rows=1488, 实际解析 1489 行, 其中跨页重复日期 1 行
- `tx/sh688256` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688300` [meta_row_count_mismatch] meta n_rows=1651, 实际解析 1653 行, 其中跨页重复日期 2 行
- `tx/sh688300` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sh688313` [meta_row_count_mismatch] meta n_rows=1462, 实际解析 1463 行, 其中跨页重复日期 1 行
- `tx/sh688313` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230509']
- `tx/sh688361` [meta_row_count_mismatch] meta n_rows=801, 实际解析 802 行, 其中跨页重复日期 1 行
- `tx/sh688361` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688498` [meta_row_count_mismatch] meta n_rows=898, 实际解析 899 行, 其中跨页重复日期 1 行
- `tx/sh688498` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688521` [meta_row_count_mismatch] meta n_rows=1457, 实际解析 1458 行, 其中跨页重复日期 1 行
- `tx/sh688521` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230508']
- `tx/sh688525` [meta_row_count_mismatch] meta n_rows=891, 实际解析 892 行, 其中跨页重复日期 1 行
- `tx/sh688525` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sh688766` [meta_row_count_mismatch] meta n_rows=1210, 实际解析 1211 行, 其中跨页重复日期 1 行
- `tx/sh688766` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230508']
- `tx/sh688981` [meta_row_count_mismatch] meta n_rows=1484, 实际解析 1485 行, 其中跨页重复日期 1 行
- `tx/sh688981` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230512']
- `tx/sz000100` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000100` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160219', '20200205', '20230522']
- `tx/sz000338` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000338` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz000338` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000338` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz000338` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000338` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz000506` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000506` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20151117', '20200113', '20230511']
- `tx/sz000636` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000636` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz000657` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000657` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160927', '20200115', '20230508']
- `tx/sz000703` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000703` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160719', '20200206', '20230522']
- `tx/sz000811` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000811` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz000988` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz000988` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz001309` [meta_row_count_mismatch] meta n_rows=1015, 实际解析 1016 行, 其中跨页重复日期 1 行
- `tx/sz001309` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz002008` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002008` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz002080` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002080` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160930', '20200115', '20230522']
- `tx/sz002081` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002081` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz002131` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002131` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161020', '20200203', '20230517']
- `tx/sz002384` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002384` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160708', '20200206', '20230522']
- `tx/sz002407` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002407` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161017', '20200206', '20230522']
- `tx/sz002428` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002428` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz002437` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002437` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160421', '20200206', '20230522']
- `tx/sz002536` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002536` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz002558` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002558` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160516', '20200206', '20230522']
- `tx/sz002580` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002580` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160419', '20200204', '20230522']
- `tx/sz002594` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz002594` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz002716` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2876 行, 其中跨页重复日期 3 行
- `tx/sz002716` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160527', '20200113', '20230522']
- `tx/sz002821` [meta_row_count_mismatch] meta n_rows=2380, 实际解析 2382 行, 其中跨页重复日期 2 行
- `tx/sz002821` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz002837` [meta_row_count_mismatch] meta n_rows=2275, 实际解析 2277 行, 其中跨页重复日期 2 行
- `tx/sz002837` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz002851` [meta_row_count_mismatch] meta n_rows=2230, 实际解析 2232 行, 其中跨页重复日期 2 行
- `tx/sz002851` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz002916` [meta_row_count_mismatch] meta n_rows=2116, 实际解析 2118 行, 其中跨页重复日期 2 行
- `tx/sz002916` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz159611` [meta_row_count_mismatch] meta n_rows=1130, 实际解析 1131 行, 其中跨页重复日期 1 行
- `tx/sz159611` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159732` [meta_row_count_mismatch] meta n_rows=1221, 实际解析 1222 行, 其中跨页重复日期 1 行
- `tx/sz159732` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159745` [meta_row_count_mismatch] meta n_rows=1267, 实际解析 1268 行, 其中跨页重复日期 1 行
- `tx/sz159745` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159755` [meta_row_count_mismatch] meta n_rows=1263, 实际解析 1264 行, 其中跨页重复日期 1 行
- `tx/sz159755` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159766` [meta_row_count_mismatch] meta n_rows=1242, 实际解析 1243 行, 其中跨页重复日期 1 行
- `tx/sz159766` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159819` [meta_row_count_mismatch] meta n_rows=1442, 实际解析 1443 行, 其中跨页重复日期 1 行
- `tx/sz159819` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159852` [meta_row_count_mismatch] meta n_rows=1350, 实际解析 1351 行, 其中跨页重复日期 1 行
- `tx/sz159852` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159865` [meta_row_count_mismatch] meta n_rows=1336, 实际解析 1337 行, 其中跨页重复日期 1 行
- `tx/sz159865` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159869` [meta_row_count_mismatch] meta n_rows=1337, 实际解析 1338 行, 其中跨页重复日期 1 行
- `tx/sz159869` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159870` [meta_row_count_mismatch] meta n_rows=1339, 实际解析 1340 行, 其中跨页重复日期 1 行
- `tx/sz159870` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159915` [meta_row_count_mismatch] meta n_rows=3579, 实际解析 3583 行, 其中跨页重复日期 4 行
- `tx/sz159915` [duplicate_kline_dates_across_pages] 跨页重复日期 4 行, 例: ['20130712', '20161024', '20200205', '20230522']
- `tx/sz159949` [meta_row_count_mismatch] meta n_rows=2459, 实际解析 2462 行, 其中跨页重复日期 3 行
- `tx/sz159949` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161026', '20200207', '20230523']
- `tx/sz159985` [meta_row_count_mismatch] meta n_rows=1638, 实际解析 1640 行, 其中跨页重复日期 2 行
- `tx/sz159985` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200207', '20230523']
- `tx/sz159992` [meta_row_count_mismatch] meta n_rows=1555, 实际解析 1556 行, 其中跨页重复日期 1 行
- `tx/sz159992` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159996` [meta_row_count_mismatch] meta n_rows=1573, 实际解析 1574 行, 其中跨页重复日期 1 行
- `tx/sz159996` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz159998` [meta_row_count_mismatch] meta n_rows=1554, 实际解析 1555 行, 其中跨页重复日期 1 行
- `tx/sz159998` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230523']
- `tx/sz300058` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300058` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz300189` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300189` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160719', '20200117', '20230522']
- `tx/sz300274` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300274` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz300274` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300274` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz300274` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300274` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz300285` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300285` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160711', '20200206', '20230522']
- `tx/sz300308` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 3200 行, 其中跨页重复日期 3 行
- `tx/sz300308` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161018', '20200206', '20230522']
- `tx/sz300394` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2797 行, 其中跨页重复日期 3 行
- `tx/sz300394` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160930', '20200206', '20230522']
- `tx/sz300395` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2916 行, 其中跨页重复日期 3 行
- `tx/sz300395` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz300454` [meta_row_count_mismatch] meta n_rows=2018, 实际解析 2020 行, 其中跨页重复日期 2 行
- `tx/sz300454` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300475` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2706 行, 其中跨页重复日期 3 行
- `tx/sz300475` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20160905', '20200117', '20230522']
- `tx/sz300476` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2729 行, 其中跨页重复日期 3 行
- `tx/sz300476` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161018', '20200206', '20230522']
- `tx/sz300489` [meta_row_count_mismatch] meta n_rows=2600, 实际解析 2711 行, 其中跨页重复日期 3 行
- `tx/sz300489` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161011', '20200122', '20230515']
- `tx/sz300502` [meta_row_count_mismatch] meta n_rows=2553, 实际解析 2556 行, 其中跨页重复日期 3 行
- `tx/sz300502` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161025', '20200206', '20230522']
- `tx/sz300548` [meta_row_count_mismatch] meta n_rows=2403, 实际解析 2406 行, 其中跨页重复日期 3 行
- `tx/sz300548` [duplicate_kline_dates_across_pages] 跨页重复日期 3 行, 例: ['20161019', '20200123', '20230522']
- `tx/sz300570` [meta_row_count_mismatch] meta n_rows=2368, 实际解析 2370 行, 其中跨页重复日期 2 行
- `tx/sz300570` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300604` [meta_row_count_mismatch] meta n_rows=2271, 实际解析 2273 行, 其中跨页重复日期 2 行
- `tx/sz300604` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200115', '20230522']
- `tx/sz300620` [meta_row_count_mismatch] meta n_rows=2296, 实际解析 2298 行, 其中跨页重复日期 2 行
- `tx/sz300620` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200115', '20230508']
- `tx/sz300666` [meta_row_count_mismatch] meta n_rows=2221, 实际解析 2223 行, 其中跨页重复日期 2 行
- `tx/sz300666` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200121', '20230515']
- `tx/sz300672` [meta_row_count_mismatch] meta n_rows=2200, 实际解析 2202 行, 其中跨页重复日期 2 行
- `tx/sz300672` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200115', '20230508']
- `tx/sz300684` [meta_row_count_mismatch] meta n_rows=2108, 实际解析 2110 行, 其中跨页重复日期 2 行
- `tx/sz300684` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300684` [meta_row_count_mismatch] meta n_rows=2108, 实际解析 2110 行, 其中跨页重复日期 2 行
- `tx/sz300684` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300750` [meta_row_count_mismatch] meta n_rows=2000, 实际解析 2002 行, 其中跨页重复日期 2 行
- `tx/sz300750` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300750` [meta_row_count_mismatch] meta n_rows=2000, 实际解析 2002 行, 其中跨页重复日期 2 行
- `tx/sz300750` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300757` [meta_row_count_mismatch] meta n_rows=1838, 实际解析 1840 行, 其中跨页重复日期 2 行
- `tx/sz300757` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20191231', '20230508']
- `tx/sz300759` [meta_row_count_mismatch] meta n_rows=1844, 实际解析 1846 行, 其中跨页重复日期 2 行
- `tx/sz300759` [duplicate_kline_dates_across_pages] 跨页重复日期 2 行, 例: ['20200206', '20230522']
- `tx/sz300857` [meta_row_count_mismatch] meta n_rows=1483, 实际解析 1484 行, 其中跨页重复日期 1 行
- `tx/sz300857` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz300903` [meta_row_count_mismatch] meta n_rows=1416, 实际解析 1417 行, 其中跨页重复日期 1 行
- `tx/sz300903` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz301018` [meta_row_count_mismatch] meta n_rows=1253, 实际解析 1254 行, 其中跨页重复日期 1 行
- `tx/sz301018` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz301165` [meta_row_count_mismatch] meta n_rows=920, 实际解析 921 行, 其中跨页重复日期 1 行
- `tx/sz301165` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz301171` [meta_row_count_mismatch] meta n_rows=977, 实际解析 978 行, 其中跨页重复日期 1 行
- `tx/sz301171` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230517']
- `tx/sz301217` [meta_row_count_mismatch] meta n_rows=1115, 实际解析 1116 行, 其中跨页重复日期 1 行
- `tx/sz301217` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz301308` [meta_row_count_mismatch] meta n_rows=990, 实际解析 991 行, 其中跨页重复日期 1 行
- `tx/sz301308` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `tx/sz301396` [meta_row_count_mismatch] meta n_rows=926, 实际解析 927 行, 其中跨页重复日期 1 行
- `tx/sz301396` [duplicate_kline_dates_across_pages] 跨页重复日期 1 行, 例: ['20230522']
- `xiaodefa/adj_factor` [adj_factor_decrease] 13160 个 (股票内) 复权因子下降点; 最大下降例: [{'ts_code': '600087.SH', 'trade_date': '20180816', 'drop': -18.263, 'from': 19.263, 'to': 1.0}, {'ts_code': '600656.SH', 'trade_date': '20180816', 'drop': -16.771, 'from': 17.771, 'to': 1.0
- `xiaodefa/block_trade` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date', 'price', 'vol'] 重复: 49994 个键 / 127449 行
- `xiaodefa/cyq_perf` [bulk_scan_failed_perfile_fallback] ComputeError: schema names differ: got ts_code, expected trade_date
- `xiaodefa/daily_info` [duplicate_primary_key_rows] 主键 ['trade_date'] 重复: 3088 个键 / 61441 行
- `xiaodefa/dc_daily` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date'] 重复: 17123 个键 / 34246 行
- `xiaodefa/fund_basic` [duplicate_primary_key_rows] 主键 ['ts_code'] 重复: 32978 个键 / 65956 行
- `xiaodefa/hk_hold` [duplicate_primary_key_rows] 主键 ['trade_date', 'ts_code'] 重复: 240 个键 / 480 行
- `xiaodefa/hm_detail` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date'] 重复: 56973 个键 / 226369 行
- `xiaodefa/index_member_all` [duplicate_primary_key_rows] 主键 ['ts_code'] 重复: 1649 个键 / 3725 行
- `xiaodefa/moneyflow` [bulk_scan_failed_perfile_fallback] ComputeError: schema names differ: got trade_date, expected ts_code
- `xiaodefa/namechange` [duplicate_primary_key_rows] 主键 ['ts_code', 'start_date', 'change_reason'] 重复: 13507 个键 / 29672 行
- `xiaodefa/pledge_detail` [not_in_inventory] 批次未在 data/_meta/inventory.json 登记
- `xiaodefa/st` [duplicate_primary_key_rows] 主键 ['ts_code'] 重复: 266 个键 / 763 行
- `xiaodefa/stk_limit` [bulk_scan_failed_perfile_fallback] ComputeError: schema names differ: got 20220705, expected trade_date
- `xiaodefa/stk_surv` [duplicate_primary_key_rows] 主键 ['ts_code'] 重复: 3956 个键 / 385579 行
- `xiaodefa/suspend_d` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date'] 重复: 77 个键 / 154 行
- `xiaodefa/sw_daily` [bulk_scan_failed_perfile_fallback] ComputeError: schema names differ: got trade_date, expected ts_code
- `xiaodefa/sz_daily_info` [duplicate_primary_key_rows] 主键 ['trade_date'] 重复: 3080 个键 / 45274 行
- `xiaodefa/tdx_index` [duplicate_primary_key_rows] 主键 ['ts_code', 'trade_date'] 重复: 132 个键 / 264 行
- `xiaodefa/top_list` [not_in_inventory] 批次未在 data/_meta/inventory.json 登记
- `xiaodefa/trade_cal` [frozen_window_rows_reference_calendar] 日期列 cal_date 有 2190 行 > 2024-12-31 (max=20261231); 冻结边界审查: 只报告不删除; 参考日历类数据, 2025+ 为日历定义而非行情观测

### info

- `bigquant/minute-bulk-20260915-1` [inventory_bytes_diff] 登记 7519B, 实际 87780B
- `bigquant/minute-bulk-20260915-1` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `tushare/balancesheet` [empty_csv_chunks] 5 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_000683.SZ.csv', 'chunk_000697.SZ.csv', 'chunk_600631.SH.csv', 'chunk_688566.SH.csv', 'chunk_T600018.SH.csv']; 未计入行数统计
- `tushare/balancesheet` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/balancesheet` [duplicate_rows_version_snapshots] 主键 ['ts_code', 'end_date', 'report_type'] 重复 138 行, 但 ['ts_code', 'end_date', 'report_type', 'update_flag'] 下唯一 (update_flag 版本快照, 非缺陷; 使用时须按 update_flag 取最新)
- `tushare/cashflow` [empty_csv_chunks] 18 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_000412.SZ.csv', 'chunk_000508.SZ.csv', 'chunk_000542.SZ.csv', 'chunk_000618.SZ.csv', 'chunk_000763.SZ.csv']; 未计入行数统计
- `tushare/cashflow` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/cashflow` [duplicate_rows_version_snapshots] 主键 ['ts_code', 'end_date', 'report_type'] 重复 200 行, 但 ['ts_code', 'end_date', 'report_type', 'update_flag'] 下唯一 (update_flag 版本快照, 非缺陷; 使用时须按 update_flag 取最新)
- `tushare/daily_basic` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/daily_basic` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/disclosure_date` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/dividend` [empty_csv_chunks] 462 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_20180102.csv', 'chunk_20180104.csv', 'chunk_20180105.csv', 'chunk_20180108.csv', 'chunk_20180109.csv']; 未计入行数统计
- `tushare/dividend` [header_check_failed] NoDataError: empty CSV
- `tushare/dividend` [empty_csv_chunks] 199 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_20150105.csv', 'chunk_20150107.csv', 'chunk_20150108.csv', 'chunk_20150112.csv', 'chunk_20150113.csv']; 未计入行数统计
- `tushare/dividend` [header_check_failed] NoDataError: empty CSV
- `tushare/events` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `tushare/express` [empty_csv_chunks] 7 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_period_20200331.csv', 'chunk_period_20200930.csv', 'chunk_period_20211231.csv', 'chunk_period_20221231.csv', 'chunk_period_20241231.csv']; 未计入行数统计
- `tushare/express` [header_check_failed] NoDataError: empty CSV
- `tushare/fina_indicator` [empty_csv_chunks] 3 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_000069.SZ.csv', 'chunk_688543.SH.csv', 'chunk_T600018.SH.csv']; 未计入行数统计
- `tushare/fina_indicator` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/forecast` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/income` [empty_csv_chunks] 4 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_600482.SH.csv', 'chunk_600631.SH.csv', 'chunk_600802.SH.csv', 'chunk_T600018.SH.csv']; 未计入行数统计
- `tushare/income` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/income` [duplicate_rows_version_snapshots] 主键 ['ts_code', 'end_date', 'report_type'] 重复 52 行, 但 ['ts_code', 'end_date', 'report_type', 'update_flag'] 下唯一 (update_flag 版本快照, 非缺陷; 使用时须按 update_flag 取最新)
- `tushare/margin_detail` [empty_csv_chunks] 1 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_20260909.csv']; 未计入行数统计
- `tushare/margin_detail` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/r3` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `tushare/repurchase` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/share_float` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/statements` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `tushare/stk_holdertrade` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/stock_basic` [empty_csv_chunks] 1 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_P.csv']; 未计入行数统计
- `tushare/sw_index_daily` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/top_inst` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `tushare/top_list` [empty_csv_chunks] 1 个 0 字节空 CSV(如按日抓取无数据日), 例: ['chunk_20260909.csv']; 未计入行数统计
- `tushare/top_list` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/20260913-1` [no_data_files] 无 csv/parquet 数据文件; 仅 6 个其他文件
- `xiaodefa/20260914-300114-status` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `xiaodefa/20260914-minute-interface-probe` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `xiaodefa/adj_factor` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/block_trade` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/ccass_hold` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/ci_daily` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/cn_cpi` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/cn_m` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/cn_pmi` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/cn_ppi` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/daily_info` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/dc_daily` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/ggt_daily` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/hk_hold` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/hm_detail` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/hs_const` [no_data_files] 无 csv/parquet 数据文件; 仅 0 个其他文件
- `xiaodefa/idx_factor_pro` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/limit_list_d` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/minute-repairs-20260913-3` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `xiaodefa/minute-repairs-20260913-4` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `xiaodefa/minute-repairs-20260913-5` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `xiaodefa/minute-repairs-20260913-6` [no_data_files] 无 csv/parquet 数据文件; 仅 1 个其他文件
- `xiaodefa/sf_month` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/stk_auction_c` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/stk_auction_o` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/stk_nineturn` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/stk_surv` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/stock_hsgt` [no_data_files] 无 csv/parquet 数据文件; 仅 0 个其他文件
- `xiaodefa/suspend_d` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/sz_daily_info` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/ths_daily` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/top10_floatholders` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
- `xiaodefa/top10_holders` [manifest_rows_off_by_one_convention] manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷
