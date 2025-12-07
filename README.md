# 🧾 Invoice Processing Agent

An intelligent, end-to-end invoice processing system built with **LangGraph**, **OpenAI**, and **Model Context Protocol (MCP)**. This agent automates the complete invoice lifecycle from OCR extraction to ERP posting, with human-in-the-loop (HITL) checkpoints for critical decisions.

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-latest-green.svg)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-orange.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-teal.svg)

---

## 🎯 Overview

This project demonstrates a production-ready invoice processing workflow that:
- **Intelligently selects OCR tools** using LLM reasoning (Tesseract vs EasyOCR)
- **Performs 2-way matching** against purchase orders
- **Pauses for human review** when invoices don't match
- **Posts to ERP systems** with accounting entries
- **Sends notifications** via email (SendGrid)
- **Maintains full audit trail** in PostgreSQL

Built as a **LangGraph state machine** with **MCP clients** for external integrations.

---

## 🏗️ Architecture

### **LangGraph Workflow**

```
INGEST → EXTRACT → CLASSIFY → ENRICH → VALIDATE → RETRIEVE → MATCH
                                                                  ↓
                                                    [Match Failed? → HITL Checkpoint]
                                                                  ↓
                                              RECONCILE → APPROVE → POST → NOTIFY → COMPLETE
```

### **Key Components**

| Component | Purpose |
|-----------|---------|
| **LangGraph Nodes** | 13 deterministic processing stages |
| **MCP Clients** | ATLAS (external data) + COMMON (internal utilities) |
| **Bigtool Picker** | LLM-based OCR selection + YAML-based tool selection |
| **FastAPI Server** | REST API + Web UI for workflow management |
| **PostgreSQL** | State persistence, checkpoints, audit logs |

---

## ✨ Features

### **🤖 LLM-Powered Intelligence**
- **Bigtool Picker**: OpenAI GPT-4o-mini selects optimal OCR tool based on invoice characteristics
- **Langie Agent**: Structured decision-making with agent personality

### **📄 OCR & Extraction**
- **Tesseract OCR**: Fast processing for high-quality printed invoices
- **EasyOCR**: Deep learning for handwriting and low-quality images
- **Automatic parsing**: Vendor, invoice number, date, line items, totals

### **🔍 2-Way Matching**
- Match invoices against purchase orders (PO)
- Compute match scores with tolerance thresholds
- Evidence-based matching (vendor, amount, line items)

### **👤 Human-in-the-Loop (HITL)**
- **Checkpoint system**: Pauses workflow when match fails
- **Review UI**: Web interface for human decisions (Accept/Reject)
- **Email notifications**: Alerts reviewers via SendGrid

### **💼 ERP Integration**
- **Mock ERP**: Demo-ready ERP posting
- **Accounting entries**: Automatic GL entry generation
- **Transaction IDs**: Full audit trail

### **📊 Dashboard & Monitoring**
- **Real-time stats**: Processed invoices, success rates
- **Recent invoices**: View all processed invoices
- **Execution logs**: Filtered logs for frontend display

---

## 🚀 Quick Start

### **Prerequisites**

- Python 3.9+
- PostgreSQL
- Tesseract OCR
- OpenAI API key
- SendGrid API key (optional, for emails)

### **Installation**

```bash
# Clone repository
git clone https://github.com/rohithsiddi/invoice-processing-agent.git
cd invoice-processing-agent

# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR
# macOS
brew install tesseract

# Ubuntu
sudo apt-get install tesseract-ocr

# Windows
 Download from: https://github.com/UB-Mannheim/tesseract/wiki

# Install EasyOCR (included in requirements.txt)
# EasyOCR will be installed via pip, no additional system dependencies needed
# Note: For GPU support, install PyTorch with CUDA
```

### **Configuration**

Create a `.env` file:

```env
# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/invoices

# SendGrid (optional)
SENDGRID_API_KEY=your_sendgrid_api_key
SENDGRID_FROM_EMAIL=noreply@yourcompany.com

# Reviewer emails
REVIEWER_EMAILS=reviewer@company.com

# Thresholds
MATCH_THRESHOLD=0.85
TOLERANCE_PERCENTAGE=5.0
AUTO_APPROVE_THRESHOLD=1000.00
```

### **Database Setup**

```bash
# Initialize database
PYTHONPATH=. python -c "from core.models.database import init_db; init_db()"
```

### **Run the Application**

```bash
# Start the server
PYTHONPATH=. python app/api/main.py

# Server runs on http://localhost:8000
```

---

## 📖 Usage

### **1. Upload Invoice via Web UI**

Navigate to `http://localhost:8000` and upload an invoice image (JPG, PNG, PDF).

### **2. Monitor Workflow**

Watch the terminal for clean, stage-separated logs:

```
============================================================
Starting node: EXTRACT
============================================================
LLM BIGTOOL PICKER - OCR Tool Selection
LLM Selected: tesseract
Completed node: EXTRACT
------------------------------------------------------------
```

### **3. Handle HITL Checkpoints**

If invoice doesn't match PO:
1. Check email for review link
2. Open review UI: `http://localhost:8000/review/{checkpoint_id}`
3. Accept or Reject with notes
4. Workflow resumes automatically

### **4. View Final Output**

Check `outputs/` folder for final JSON:

```bash
outputs/INV-2024-001_final_output.json
```

---

## 🗂️ Project Structure

```
Invoice-Processing-Agent/
├── app/
│   ├── api/              # FastAPI server + endpoints
│   ├── nodes/            # LangGraph workflow nodes (13 nodes)
│   └── workflow/         # Workflow orchestration
├── core/
│   ├── config/           # Configuration (config.py, tools.yaml)
│   ├── models/           # Database models + state definition
│   └── utils/            # Logging, error handling, helpers
├── integrations/
│   ├── mcp/              # MCP clients (ATLAS + COMMON)
│   └── tools/            # Bigtool picker (unified LLM + YAML)
├── data/
│   ├── samples/          # Mock PO/GRN/history data
│   └── uploads/          # Uploaded invoices
├── outputs/              # Final JSON outputs
└── logs/                 # Application logs
```

---

## 🔧 Key Technologies

| Technology | Purpose |
|------------|---------|
| **LangGraph** | State machine workflow orchestration |
| **OpenAI GPT-4o-mini** | LLM-based tool selection |
| **FastAPI** | REST API + Web server |
| **PostgreSQL** | Database (invoices, checkpoints, audit) |
| **Tesseract OCR** | Fast OCR for printed text |
| **EasyOCR** | Deep learning OCR for handwriting |
| **SendGrid** | Email notifications |
| **SQLAlchemy** | ORM for database |
| **Pydantic** | Data validation |

---

## 📊 Workflow Stages

| Stage | Node | Purpose |
|-------|------|---------|
| 1 | **INGEST** | Upload and validate invoice file |
| 2 | **EXTRACT** | OCR extraction with LLM tool selection |
| 3 | **CLASSIFY** | Classify invoice type |
| 4 | **ENRICH** | Enrich vendor data via ATLAS MCP |
| 5 | **VALIDATE** | Validate invoice schema |
| 6 | **RETRIEVE** | Fetch POs, GRNs, history from ERP |
| 7 | **MATCH** | 2-way matching against PO |
| 8 | **CHECKPOINT** | HITL pause if match fails |
| 9 | **HITL_DECISION** | Process human review decision |
| 10 | **RECONCILE** | Build accounting entries |
| 11 | **APPROVE** | Auto-approve or require approval |
| 12 | **POST** | Post to ERP system |
| 13 | **NOTIFY** | Send email notifications |
| 14 | **COMPLETE** | Finalize and save output |

---

## 🎨 Demo Features

- ✅ **Clean terminal logs** with stage separators
- ✅ **LLM tool selection** with reasoning logs
- ✅ **Automatic JSON output** saved to `outputs/`
- ✅ **Web dashboard** for monitoring
- ✅ **Email notifications** for HITL reviews
- ✅ **Full audit trail** in database

---

## 👨‍💻 Author

**Rohith Siddi**
- GitHub: [@rohithsiddi](https://github.com/rohithsiddi)
- Email: rohithsiddi7@gmail.com

---

## 🙏 Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- Powered by [OpenAI](https://openai.com)
---
