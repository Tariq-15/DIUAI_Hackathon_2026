# Prohori Fraud Detection Evaluation Report

- **Test Set Transactions:** 151,452
- **Test Fraud Instances:** 1,809 (1.19%)
- **Primary Evaluation Benchmark:** False Alert Rate (FAR) ≤ 5.0%

## 1. Model Performance Benchmark (Test Set)

| Model | ROC-AUC | PR-AUC (AP) | Recall @ 5% FAR | Precision @ 5% FAR | Best F1 | Threshold @ 5% FAR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **LightGBM** | 1.0000 | 0.9979 | **100.00%** | 53.22% | 0.9931 | `0.001` |
| **XGBoost** | 0.9999 | 0.9953 | **100.00%** | 75.85% | 0.9826 | `0.001` |
| **Fused Ensemble** | 1.0000 | 0.9963 | **100.00%** | 20.01% | 0.9928 | `0.094` |

## 2. Detection Recall by Fraud Typology (@ 5% FAR)

| Typology Code | Fraud Scenario Family | Total Test Samples | Detected | Detection Recall |
| :--- | :--- | :---: | :---: | :---: |
| `S1` | Account Takeover (ATO) | 428 | 428 | **100.00%** |
| `S2` | Agent Churn / Collusion | 72 | 72 | **100.00%** |
| `S3` | Split Cash-In / Mule Funnel | 22 | 22 | **100.00%** |
| `S4` | Fast Cash-Out / Ponzi Drain | 24 | 24 | **100.00%** |
| `S5` | Dormant Account Wakeup | 1,248 | 1,248 | **100.00%** |
| `S6` | Inflow / Outflow Mismatch | 9 | 9 | **100.00%** |
| `S7` | Structural / Ring Anomaly | 6 | 6 | **100.00%** |

## 3. False Alarm Resilience on Benign Lookalikes

| Cohort | Total Transactions | False Positives | False Alarm Rate (FAR) |
| :--- | :---: | :---: | :---: |
| Standard Benign | 148,327 | 6,219 | **4.19%** |
| Benign Lookalike | 1,316 | 1,014 | **77.05%** |


*Generated automatically by Prohori Evaluation Suite.*