#!/usr/bin/env python3
"""
PMCore Overnight Evaluation & Auto-Adjustment
==============================================
Runs 200 full-pipeline tests, scores outputs on 10 dimensions,
identifies systematic issues, makes safe inference-level fixes,
re-tests, and writes a final report.

Run on thing1:
    uv run python overnight_eval.py
"""

import json
import time
import random
import re
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict, Counter
from typing import Optional

BASE_URL    = "http://localhost:8765"
REPORT_PATH = Path("eval_report_v6.md")
LOG_PATH    = Path("retrain_logs_v6/overnight_eval.log")
TIMEOUT     = 180   # seconds per request

LOG_PATH.parent.mkdir(exist_ok=True)
_log_fh = open(LOG_PATH, "w", buffering=1)

def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log_fh.write(line + "\n")

# ─────────────────────────────────────────────────────────────────────────────
# 200 Diverse Test Projects
# ─────────────────────────────────────────────────────────────────────────────

PROJECTS = [
    # Construction & Real Estate
    ("Build a 40-story luxury residential tower in downtown Chicago. Budget 250M, 36 months, 120-person team.", "Write a project kickoff email to the project team."),
    ("Renovate a historic 1920s courthouse into modern office space. Budget 18M, 18 months.", "Write a weekly status report for stakeholders."),
    ("Construct a 500-bed hospital including OR suites, ICU, and radiology. Budget 400M, 48 months.", "Write a risk escalation memo to the executive sponsor."),
    ("Build a solar farm with 200MW capacity across 800 acres. Budget 180M, 24 months.", "Write an executive summary for the board."),
    ("Develop a 300-unit mixed-use apartment complex with retail ground floor. Budget 75M, 30 months.", "Write a project kickoff announcement."),
    ("Retrofit a 1970s office park to LEED Platinum standards. Budget 12M, 14 months.", "Write a weekly status report."),
    ("Build a regional distribution center, 500K sq ft, with automated conveyor systems. Budget 90M, 20 months.", "Write an executive summary for the board."),
    ("Renovate hotel lobby, restaurant, and 200 guest rooms. Budget 8M, 6 months.", "Write a stakeholder status update."),
    ("Construct underground parking garage, 800 spaces, beneath existing plaza. Budget 35M, 18 months.", "Write a risk escalation to senior leadership."),
    ("Develop oceanfront resort — 150 villas, spa, marina. Budget 120M, 36 months.", "Write a project kickoff email."),

    # Technology & Software
    ("Migrate enterprise from on-prem SAP to SAP S4/HANA cloud. 3000 users, Budget 15M, 18 months.", "Write a weekly status report."),
    ("Build a real-time fraud detection ML platform processing 10M transactions/day. Budget 6M, 12 months.", "Write an executive summary for the board."),
    ("Develop a patient portal mobile app for health system with 500K patients. Budget 4M, 9 months.", "Write a project kickoff email."),
    ("Re-platform legacy monolith into microservices on AWS. 200 services, Budget 8M, 24 months.", "Write a risk escalation memo."),
    ("Build autonomous vehicle sensor fusion software stack. Budget 22M, 36 months.", "Write a board update on project status."),
    ("Deploy zero-trust cybersecurity architecture across 50 office locations. Budget 3M, 12 months.", "Write a weekly status report."),
    ("Create AI-powered customer service chatbot for 5M customer base. Budget 2M, 8 months.", "Write an executive summary."),
    ("Build enterprise data lake consolidating 40 source systems. Budget 5M, 15 months.", "Write a project kickoff email."),
    ("Implement DevSecOps pipeline and shift-left testing across 300 developers. Budget 1.5M, 10 months.", "Write a stakeholder status update."),
    ("Develop blockchain supply chain tracking for pharmaceutical distributor. Budget 7M, 18 months.", "Write a risk escalation."),
    ("Build SaaS HR platform from scratch for SMB market, Series A funded, 18 months.", "Write a kickoff email to the engineering team."),
    ("Modernize mainframe COBOL systems to Java microservices. 2M lines of code, Budget 30M, 48 months.", "Write an executive summary for the board."),
    ("Deploy IoT sensors across 200-factory manufacturing network, real-time OEE dashboards. Budget 4M, 12 months.", "Write a weekly status update."),
    ("Build omnichannel e-commerce platform for retailer with 2000 SKUs. Budget 3M, 10 months.", "Write a project kickoff announcement."),
    ("Implement AI demand forecasting replacing spreadsheet-based process. Budget 1.2M, 8 months.", "Write a risk escalation to the CFO."),

    # Finance & Banking
    ("Core banking system replacement for 300K-customer community bank. Budget 12M, 30 months.", "Write a board update."),
    ("Launch neobank mobile app — checking, savings, crypto. Budget 20M, 18 months.", "Write a project kickoff email."),
    ("Implement Basel IV regulatory capital reporting system. Budget 8M, 14 months.", "Write a weekly status report."),
    ("Open 40 new retail bank branches across Southeast. Budget 25M, 24 months.", "Write an executive summary."),
    ("Migrate wealth management platform to cloud. 50B AUM, Budget 6M, 12 months.", "Write a risk escalation."),
    ("Build real-time payment processing system meeting FedNow standards. Budget 10M, 15 months.", "Write a kickoff announcement."),
    ("Implement AML transaction monitoring system for investment bank. Budget 4M, 10 months.", "Write a board update on risks."),
    ("Launch small business lending platform with automated underwriting. Budget 5M, 12 months.", "Write a weekly status report."),
    ("Consolidate 4 regional insurance subsidiaries onto single platform. Budget 18M, 24 months.", "Write an executive summary."),
    ("Deploy robo-advisor platform for retail investors. Budget 3M, 9 months.", "Write a project kickoff email."),

    # Healthcare & Life Sciences
    ("Implement Epic EHR across 8-hospital health system, 12000 staff. Budget 35M, 30 months.", "Write a board update."),
    ("Launch Phase III clinical trial for oncology drug, 3000 patients, 30 sites. Budget 80M, 48 months.", "Write a risk escalation to the executive team."),
    ("Build regional telehealth platform serving rural communities. Budget 2M, 10 months.", "Write a weekly status report."),
    ("Construct new sterile pharmaceutical manufacturing facility. Budget 120M, 36 months.", "Write a project kickoff announcement."),
    ("Deploy AI radiology reading assistance across 15 hospitals. Budget 3M, 8 months.", "Write an executive summary."),
    ("Implement value-based care program for 200K attributed lives. Budget 4M, 18 months.", "Write a stakeholder update."),
    ("Build medical device remote monitoring platform for cardiac implants. Budget 5M, 12 months.", "Write a kickoff email."),
    ("Commission gene therapy manufacturing cleanroom facility. Budget 45M, 24 months.", "Write a board update."),
    ("Launch pharmaceutical DTC e-commerce with cold-chain logistics. Budget 3M, 9 months.", "Write a weekly status report."),
    ("Implement RPA across claims processing — 1M claims/month. Budget 1.5M, 6 months.", "Write a risk escalation."),

    # Manufacturing & Operations
    ("Implement Industry 4.0 transformation across 5 factories. Budget 25M, 36 months.", "Write an executive summary for the board."),
    ("Launch new electric vehicle production line, 50K units/year capacity. Budget 200M, 30 months.", "Write a project kickoff email."),
    ("Deploy predictive maintenance AI on 2000 CNC machines. Budget 3M, 8 months.", "Write a weekly status report."),
    ("Consolidate 6 distribution centers into 2 mega-DCs. Budget 30M, 18 months.", "Write a risk escalation."),
    ("Implement lean manufacturing across 8 plants — VSM, kaizen, 5S. Budget 2M, 12 months.", "Write a board update."),
    ("Build contract manufacturing facility for defense electronics. Budget 60M, 24 months.", "Write a project kickoff announcement."),
    ("Automate assembly line with collaborative robots. 12 stations, Budget 8M, 10 months.", "Write a weekly status report."),
    ("Implement ISO 9001:2015 quality management system company-wide. Budget 800K, 8 months.", "Write an executive summary."),
    ("Launch 3D printing production facility for aerospace components. Budget 15M, 18 months.", "Write a kickoff email."),
    ("Deploy ERP (Oracle) across global manufacturing operations, 40 plants. Budget 50M, 36 months.", "Write a risk escalation to leadership."),

    # Retail & Consumer
    ("Relaunch retail brand — new store concept, 200 location rollout. Budget 40M, 24 months.", "Write a board update."),
    ("Implement unified commerce platform — POS, e-commerce, inventory. Budget 6M, 12 months.", "Write a weekly status report."),
    ("Launch private label product line — 50 SKUs, 3 countries. Budget 5M, 10 months.", "Write a kickoff announcement."),
    ("Build AI-powered personalization engine for 10M-customer e-commerce site. Budget 4M, 12 months.", "Write an executive summary."),
    ("Open flagship experiential retail store, 20K sq ft. Budget 3M, 8 months.", "Write a risk escalation."),
    ("Deploy RFID inventory tracking across 400 stores. Budget 8M, 14 months.", "Write a board update."),
    ("Launch subscription box service — fulfillment, logistics, tech stack. Budget 2M, 6 months.", "Write a project kickoff email."),
    ("Implement dynamic pricing engine across 50K online SKUs. Budget 1.5M, 8 months.", "Write a weekly status report."),
    ("Build loyalty rewards platform for grocery chain, 2M members. Budget 3M, 10 months.", "Write a kickoff announcement."),
    ("Consolidate 3 retail ERPs post-acquisition. Budget 12M, 18 months.", "Write an executive summary."),

    # Energy & Infrastructure
    ("Construct offshore wind farm, 500MW, 80 turbines. Budget 2B, 60 months.", "Write a board update."),
    ("Build battery energy storage system, 200MWh, utility-scale. Budget 150M, 18 months.", "Write a project kickoff email."),
    ("Replace aging water treatment infrastructure for city of 500K. Budget 90M, 36 months.", "Write a risk escalation."),
    ("Implement smart grid across 400K-meter distribution network. Budget 75M, 24 months.", "Write an executive summary."),
    ("Build LNG terminal with 2 berths and 300K m3 storage. Budget 400M, 48 months.", "Write a board update."),
    ("Deploy EV charging network — 1000 fast-chargers, 200 locations. Budget 25M, 18 months.", "Write a weekly status report."),
    ("Upgrade electricity substation, 345kV, serving metro area. Budget 35M, 24 months.", "Write a kickoff email."),
    ("Build fiber-optic network across rural tri-county area, 2000 miles. Budget 45M, 30 months.", "Write a board update."),
    ("Construct biomass power plant, 50MW. Budget 120M, 36 months.", "Write a risk escalation."),
    ("Deploy 5G private network across 10 manufacturing campuses. Budget 12M, 14 months.", "Write a weekly status report."),

    # Government & Public Sector
    ("Modernize DMV systems across 300 locations for state government. Budget 85M, 36 months.", "Write a board update."),
    ("Implement unified 911 emergency dispatch platform, 50 PSAPs. Budget 40M, 24 months.", "Write a risk escalation."),
    ("Build public transit smart card payment system, 3M daily riders. Budget 30M, 18 months.", "Write a project kickoff."),
    ("Deploy body cameras and evidence management for 5000-officer police department. Budget 8M, 12 months.", "Write a weekly status report."),
    ("Construct new courthouse, 15 courtrooms, federal-grade security. Budget 60M, 30 months.", "Write an executive summary."),
    ("Implement benefits administration system for state unemployment agency. Budget 25M, 18 months.", "Write a risk escalation."),
    ("Build cyber defense operations center for municipal government. Budget 5M, 12 months.", "Write a board update."),
    ("Modernize public school network — 200 schools, fiber, devices. Budget 20M, 18 months.", "Write a kickoff announcement."),
    ("Implement open data portal and analytics platform for city. Budget 2M, 10 months.", "Write a weekly status report."),
    ("Deploy gunshot detection system across urban metro area. Budget 3M, 8 months.", "Write a risk escalation."),

    # Education
    ("Launch online MBA program with 20 courses, 2000 students year 1. Budget 5M, 18 months.", "Write a project kickoff email."),
    ("Implement Canvas LMS across university system, 80K students. Budget 3M, 12 months.", "Write a board update."),
    ("Build AI tutoring system for K-12 math. Budget 2M, 12 months.", "Write a weekly status report."),
    ("Renovate and expand university library, 120K sq ft. Budget 25M, 24 months.", "Write a kickoff announcement."),
    ("Deploy 1:1 device program for school district, 25K Chromebooks. Budget 4M, 6 months.", "Write an executive summary."),
    ("Launch continuing education bootcamp platform, 10 tracks. Budget 1.5M, 8 months.", "Write a project kickoff email."),
    ("Build research data repository for multi-university consortium. Budget 2M, 14 months.", "Write a weekly status report."),
    ("Implement competency-based education platform for nursing school. Budget 1M, 10 months.", "Write a risk escalation."),
    ("Expand international student services — 5 new countries, 2000 students. Budget 3M, 18 months.", "Write a board update."),
    ("Construct STEM innovation lab and makerspace, 15K sq ft. Budget 8M, 12 months.", "Write a kickoff email."),

    # Logistics & Supply Chain
    ("Implement real-time shipment visibility platform across global supply chain. Budget 4M, 12 months.", "Write an executive summary."),
    ("Build cold-chain logistics network for pharmaceutical distributor. Budget 15M, 18 months.", "Write a risk escalation."),
    ("Deploy autonomous mobile robots in 3 fulfillment centers, 500K sq ft each. Budget 20M, 14 months.", "Write a board update."),
    ("Implement control tower for 3PL managing 50 clients. Budget 3M, 10 months.", "Write a weekly status report."),
    ("Consolidate 8 regional carriers into unified TMS platform. Budget 6M, 14 months.", "Write a kickoff announcement."),
    ("Build last-mile delivery optimization for 1M deliveries/month. Budget 5M, 12 months.", "Write an executive summary."),
    ("Deploy RFID and blockchain for food traceability, farm to shelf. Budget 4M, 10 months.", "Write a board update."),
    ("Implement dynamic safety stock and replenishment AI. Budget 2M, 8 months.", "Write a weekly status report."),
    ("Build cross-docking facility, 300K sq ft, 200 dock doors. Budget 30M, 20 months.", "Write a risk escalation."),
    ("Migrate to cloud-native WMS for 10-warehouse network. Budget 4M, 12 months.", "Write a kickoff email."),

    # Media & Entertainment
    ("Launch streaming platform competing with Netflix — 10K titles, 5M subscribers year 1. Budget 50M, 24 months.", "Write a board update."),
    ("Build real-time sports betting platform for 20 states. Budget 15M, 18 months.", "Write a risk escalation."),
    ("Produce and release AAA video game — 300-person studio, 36 months, Budget 80M.", "Write a weekly status report."),
    ("Renovate broadcast production facility, 4K/HDR, IP-based infrastructure. Budget 12M, 12 months.", "Write a kickoff announcement."),
    ("Launch podcast network — 50 shows, ad sales, distribution. Budget 3M, 10 months.", "Write an executive summary."),
    ("Build fan engagement app for NFL franchise, 70K seat stadium. Budget 4M, 8 months.", "Write a project kickoff email."),
    ("Produce 10-episode scripted series for streaming, Budget 25M, 18 months.", "Write a weekly status report."),
    ("Launch eSports arena and tournament operations platform. Budget 8M, 12 months.", "Write a board update."),
    ("Build music rights management and royalty distribution platform. Budget 5M, 14 months.", "Write a risk escalation."),
    ("Develop metaverse social platform — avatars, virtual events, marketplace. Budget 30M, 24 months.", "Write an executive summary."),

    # HR & Organizational
    ("Global HR transformation — HRIS, payroll, talent management, 20K employees. Budget 12M, 24 months.", "Write a board update."),
    ("Implement remote-work policy and tooling for 5000-person company. Budget 3M, 6 months.", "Write a weekly status report."),
    ("Launch DEI program — training, reporting, hiring pipeline overhaul. Budget 2M, 18 months.", "Write a kickoff announcement."),
    ("Merge two company cultures post-acquisition, 800 employees combined. Budget 1.5M, 12 months.", "Write a risk escalation."),
    ("Deploy people analytics platform — attrition prediction, workforce planning. Budget 2M, 10 months.", "Write an executive summary."),
    ("Build internal learning management system, 50 mandatory courses. Budget 1M, 8 months.", "Write a project kickoff email."),
    ("Implement performance management OKR system company-wide. Budget 800K, 6 months.", "Write a weekly status report."),
    ("Relocate headquarters — 1200 employees, 6-floor office build-out. Budget 20M, 14 months.", "Write a board update."),
    ("Launch employee wellness platform — mental health, fitness, EAP. Budget 1M, 8 months.", "Write a kickoff email."),
    ("Implement global payroll consolidation across 15 countries. Budget 4M, 18 months.", "Write a risk escalation."),

    # Marketing & Brand
    ("Rebrand global consumer goods company — 50 product lines, 20 markets. Budget 15M, 18 months.", "Write an executive summary."),
    ("Launch integrated digital marketing platform, 200M annual impressions. Budget 5M, 12 months.", "Write a board update."),
    ("Build customer data platform unifying 8 data sources, 5M profiles. Budget 4M, 10 months.", "Write a weekly status report."),
    ("Execute global product launch — 30 countries, coordinated media. Budget 20M, 10 months.", "Write a kickoff announcement."),
    ("Implement marketing attribution model across all channels. Budget 1.5M, 8 months.", "Write a risk escalation."),
    ("Build influencer marketing platform for CPG brand. Budget 2M, 8 months.", "Write a project kickoff email."),
    ("Create content supply chain — 1000 pieces/month, 10 markets. Budget 3M, 12 months.", "Write an executive summary."),
    ("Launch ABM program targeting 500 enterprise accounts. Budget 2.5M, 12 months.", "Write a weekly status report."),
    ("Migrate to CDP and rebuild personalization engine. Budget 3M, 10 months.", "Write a board update."),
    ("Develop brand identity system for startup series B company. Budget 500K, 4 months.", "Write a kickoff email."),

    # Environmental & Sustainability
    ("Achieve net-zero carbon emissions across global operations by 2030. Budget 50M, 48 months.", "Write a board update."),
    ("Implement Scope 3 emissions tracking across 500-supplier network. Budget 3M, 12 months.", "Write a risk escalation."),
    ("Build corporate sustainability reporting platform for ESG disclosure. Budget 2M, 10 months.", "Write an executive summary."),
    ("Install EV fleet — replace 500 diesel vehicles, charging infrastructure. Budget 20M, 18 months.", "Write a weekly status report."),
    ("Construct LEED Platinum data center with 100% renewable power. Budget 80M, 24 months.", "Write a kickoff email."),
    ("Develop circular economy program — 30% packaging reduction, recycling. Budget 4M, 18 months.", "Write a board update."),
    ("Implement water recycling across 8 manufacturing facilities. Budget 6M, 14 months.", "Write a risk escalation."),
    ("Build biodiversity restoration program — 1000 acres reforestation. Budget 3M, 24 months.", "Write an executive summary."),
    ("Deploy carbon capture pilot facility, 10K tons/year. Budget 25M, 30 months.", "Write a weekly status report."),
    ("Launch sustainable sourcing program across food supply chain. Budget 2M, 12 months.", "Write a kickoff announcement."),

    # Miscellaneous / Edge Cases
    ("Decommission nuclear power plant safely. Budget 500M, 60 months.", "Write a board update on project status."),
    ("Plan and execute company IPO — systems, compliance, investor relations. Budget 8M, 12 months.", "Write a risk escalation."),
    ("Implement GDPR/CCPA compliance program across 30-country operation. Budget 5M, 14 months.", "Write a weekly status report."),
    ("Build urban air mobility (eVTOL) testing facility. Budget 40M, 24 months.", "Write a kickoff email."),
    ("Launch direct-to-consumer wine subscription — fulfillment, compliance, 50 states. Budget 2M, 8 months.", "Write an executive summary."),
    ("Migrate 10PB data archive from tape to cloud object storage. Budget 2M, 12 months.", "Write a board update."),
    ("Implement enterprise-wide AI governance framework. Budget 1.5M, 10 months.", "Write a risk escalation."),
    ("Plan and execute merger integration of two 500-person companies. Budget 10M, 18 months.", "Write a board update."),
    ("Build quantum computing research lab and talent pipeline. Budget 15M, 24 months.", "Write a kickoff email."),
    ("Launch food truck franchise brand — 50 trucks, operations manual, app. Budget 1M, 6 months.", "Write a weekly status report."),

    # More software/tech edge cases
    ("Port Windows desktop app to web SaaS for 50K users. Budget 3M, 14 months.", "Write a kickoff announcement."),
    ("Implement SOC 2 Type II certification for SaaS company. Budget 600K, 8 months.", "Write a weekly status report."),
    ("Build ML platform for real-time recommendation engine, 100M users. Budget 10M, 18 months.", "Write a board update."),
    ("Develop natural language processing API for legal document review. Budget 4M, 12 months.", "Write a risk escalation."),
    ("Migrate 2000 VM workloads from VMware to Kubernetes on GCP. Budget 3M, 10 months.", "Write an executive summary."),
    ("Build API gateway and developer portal for fintech platform. Budget 2M, 8 months.", "Write a kickoff email."),
    ("Implement ITSM platform (ServiceNow) for 5000-seat IT organization. Budget 3M, 12 months.", "Write a weekly status report."),
    ("Build autonomous drone delivery system — city pilot, 500 deliveries/day. Budget 8M, 18 months.", "Write a board update."),
    ("Launch AR/VR employee training platform for safety-critical roles. Budget 2M, 10 months.", "Write a risk escalation."),
    ("Implement graph database for fraud ring detection across 100M accounts. Budget 5M, 12 months.", "Write an executive summary."),

    # Additional projects (batch 2)
    ("Build a self-service analytics portal for 2000 business users replacing Excel. Budget 2M, 8 months.", "Write a project kickoff email."),
    ("Launch a B2B SaaS invoicing platform with NetSuite integration. Budget 3M, 12 months.", "Write a weekly status report."),
    ("Implement CMMS (computerized maintenance management) across 20 facilities. Budget 1.5M, 8 months.", "Write an executive summary."),
    ("Deploy AI quality inspection cameras on 50 production lines. Budget 4M, 10 months.", "Write a board update."),
    ("Build a real-time currency exchange trading desk system. Budget 6M, 14 months.", "Write a risk escalation."),
    ("Construct a tier-3 data center, 5MW, 2000 racks. Budget 70M, 24 months.", "Write a project kickoff announcement."),
    ("Implement continuous glucose monitoring app for 100K diabetic patients. Budget 3M, 10 months.", "Write a weekly status report."),
    ("Launch a digital twin of manufacturing plant for simulation and optimization. Budget 5M, 18 months.", "Write an executive summary."),
    ("Develop AI contract review platform for law firm with 500 attorneys. Budget 4M, 12 months.", "Write a board update."),
    ("Build a centralized secrets management and PKI platform for 5000 developers. Budget 2M, 8 months.", "Write a kickoff email."),
    ("Roll out Microsoft 365 Copilot to 10000-employee enterprise. Budget 3M, 6 months.", "Write a weekly status report."),
    ("Build an airport terminal expansion — 12 new gates, retail, lounges. Budget 250M, 36 months.", "Write a risk escalation."),
    ("Implement AI-assisted code review for 800-developer engineering org. Budget 2M, 8 months.", "Write a kickoff announcement."),
    ("Launch pet insurance product — underwriting engine, portal, claims. Budget 4M, 12 months.", "Write an executive summary."),
    ("Deploy enterprise search platform across 5M internal documents. Budget 2M, 8 months.", "Write a board update."),
    ("Build satellite internet ground station network, 30 locations. Budget 80M, 24 months.", "Write a project kickoff."),
    ("Implement financial close automation — 200 legal entities, 15 days to 5 days. Budget 3M, 10 months.", "Write a weekly status report."),
    ("Launch a franchise management platform for 500-unit food brand. Budget 2M, 8 months.", "Write a kickoff email."),
    ("Construct a vertical farming facility, 2 acres, leafy greens. Budget 12M, 18 months.", "Write an executive summary."),
    ("Build predictive wildfire risk modeling platform for utility. Budget 3M, 10 months.", "Write a risk escalation."),
    ("Implement unified namespace industrial data platform across 15 plants. Budget 4M, 14 months.", "Write a board update."),
    ("Launch telematics-based auto insurance product for 50K drivers. Budget 5M, 12 months.", "Write a weekly status report."),
    ("Deploy AI-assisted radiology triage reducing read time by 50%. Budget 2M, 8 months.", "Write a kickoff announcement."),
    ("Build carbon credit tokenization platform on public blockchain. Budget 3M, 12 months.", "Write an executive summary."),
    ("Implement automated regulatory change management system for bank. Budget 2M, 10 months.", "Write a risk escalation."),
    ("Roll out digital work instructions to 3000 shop-floor workers. Budget 2M, 8 months.", "Write a board update."),
    ("Launch an employee share purchase plan platform, 10000 participants. Budget 1.5M, 8 months.", "Write a kickoff email."),
    ("Build AI-powered lease abstraction tool for commercial real estate firm. Budget 2M, 8 months.", "Write a weekly status report."),
    ("Construct a lithium-ion battery gigafactory, 10GWh annual output. Budget 800M, 48 months.", "Write a board update."),
    ("Implement a unified master data management platform, 6 domains. Budget 4M, 16 months.", "Write an executive summary."),
    ("Launch a B2C insurance comparison marketplace. Budget 5M, 14 months.", "Write a project kickoff email."),
    ("Deploy end-to-end encryption across enterprise communication stack. Budget 1.5M, 6 months.", "Write a weekly status report."),
    ("Build a cloud-native pricing engine for airline, 100M fare lookups/day. Budget 8M, 18 months.", "Write a risk escalation."),
    ("Implement integrated workplace management system across 200 offices. Budget 3M, 12 months.", "Write a board update."),
    ("Launch a community solar program connecting 5000 residential subscribers. Budget 10M, 18 months.", "Write a kickoff announcement."),
]

assert len(PROJECTS) == 200, f"Expected 200 projects, got {len(PROJECTS)}"

# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    idx: int
    project: str
    comm_request: str
    success: bool
    error: Optional[str] = None
    latency_ms: int = 0

    # Planner scores
    planner_json_valid: bool = False
    planner_methodology: str = ""
    planner_duration_days: int = 0
    planner_num_tasks: int = 0
    planner_fallback: bool = False

    # Reasoner scores
    reasoner_health: str = ""
    reasoner_risks: int = 0
    reasoner_critical_path: int = 0
    reasoner_fallback: bool = False

    # Communicator scores
    comm_length: int = 0
    comm_type: str = ""
    comm_uses_project_name: bool = False
    comm_has_numbers: bool = False
    comm_no_placeholders: bool = False
    comm_coherent: bool = False
    comm_type_matches_request: bool = False
    comm_text: str = ""

    @property
    def score(self) -> float:
        """0-10 composite score."""
        if not self.success:
            return 0.0
        s = 0.0
        # Planner (3 pts)
        if self.planner_json_valid: s += 1.0
        if self.planner_num_tasks > 0: s += 1.0
        if not self.planner_fallback: s += 1.0
        # Reasoner (2 pts)
        if self.reasoner_health in ("green", "yellow", "red"): s += 1.0
        if self.reasoner_risks > 0: s += 1.0
        # Communicator (5 pts)
        if self.comm_length > 200: s += 1.0
        if self.comm_uses_project_name: s += 1.0
        if self.comm_has_numbers: s += 1.0
        if self.comm_no_placeholders: s += 1.0
        if self.comm_coherent: s += 1.0
        return s


def score_communication(text: str, project: str, comm_request: str) -> dict:
    """Analyze communicator prose quality."""
    if not text or len(text) < 50:
        return dict(uses_project_name=False, has_numbers=False,
                    no_placeholders=True, coherent=False, type_matches=False)

    # Extract key project words (first 4 words, skip stop words)
    stop = {"a","an","the","for","in","of","on","with","to","and","or","at","by",
            "from","into","is","are","was","were","be","been","been","as","that"}
    proj_words = [w for w in re.sub(r'[^\w\s]', '', project.lower()).split()
                  if w not in stop and len(w) > 3][:5]
    uses_proj = any(w in text.lower() for w in proj_words)

    # Contains numbers/dollar amounts
    has_numbers = bool(re.search(r'\$\d|[\d,]+\s*(month|week|day|M\b|K\b|%|staff|user|patient)', text, re.I))

    # No placeholder brackets
    no_placeholders = '[' not in text and '{' not in text

    # Coherence: multiple complete sentences, no repeating fragments
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 20]
    coherent = len(sentences) >= 3 and len(set(sentences)) >= len(sentences) * 0.7

    # Communication type matching
    req_lower = comm_request.lower()
    type_map = {
        "kickoff": ["kickoff", "kick-off", "subject: project kickoff", "kicking off", "pleased to announce"],
        "status": ["status", "weekly", "progress", "update", "this week"],
        "escalation": ["escalation", "risk", "urgent", "attention required", "action required", "escalat"],
        "board": ["board", "executive", "leadership", "governance", "strategic"],
        "closeout": ["closeout", "close-out", "completion", "handover", "handover letter", "lessons learned"],
    }
    type_matches = False
    for req_kw, output_kws in type_map.items():
        if req_kw in req_lower:
            if any(kw in text.lower() for kw in output_kws):
                type_matches = True
            break

    return dict(uses_project_name=uses_proj, has_numbers=has_numbers,
                no_placeholders=no_placeholders, coherent=coherent,
                type_matches=type_matches)


def call_api(endpoint: str, body: dict, timeout: int = TIMEOUT) -> tuple[dict, int]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}", data=data,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        result = json.loads(r.read())
    ms = int((time.time() - t0) * 1000)
    return result, ms


def run_test(idx: int, project: str, comm_request: str) -> TestResult:
    result = TestResult(idx=idx, project=project, comm_request=comm_request, success=False)
    try:
        data, ms = call_api("/plan", {
            "request": project,
            "comm_request": comm_request,
            "verbose": False,
        })
        result.latency_ms = ms
        result.success = True

        # Planner
        p = data.get("planner", {})
        tg = p.get("tasks") or {}
        result.planner_json_valid = isinstance(tg, dict) and len(tg) > 0
        result.planner_methodology = p.get("methodology", "")
        result.planner_duration_days = p.get("duration_days", 0)
        result.planner_num_tasks = p.get("num_tasks", 0)
        result.planner_fallback = bool((tg or {}).get("_fallback"))

        # Reasoner
        r = data.get("reasoner", {})
        result.reasoner_health = (r.get("overall_health") or "").lower()
        result.reasoner_risks = len(r.get("top_risks") or [])
        result.reasoner_critical_path = len(r.get("critical_path") or [])
        result.reasoner_fallback = bool((r.get("risk_analysis") or {}).get("_fallback"))

        # Communicator
        c = data.get("communicator", {})
        comm_text = c.get("communication", "")
        result.comm_length = len(comm_text)
        result.comm_type = c.get("comm_type", "")
        result.comm_text = comm_text  # store full output for report

        scores = score_communication(comm_text, project, comm_request)
        result.comm_uses_project_name = scores["uses_project_name"]
        result.comm_has_numbers      = scores["has_numbers"]
        result.comm_no_placeholders  = scores["no_placeholders"]
        result.comm_coherent         = scores["coherent"]
        result.comm_type_matches_request = scores["type_matches"]

    except Exception as e:
        result.error = str(e)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────────────────────

def analyze_results(results: list[TestResult]) -> dict:
    total = len(results)
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    scores = [r.score for r in successful]
    avg_score = sum(scores) / len(scores) if scores else 0

    issues = defaultdict(list)
    for r in successful:
        if not r.planner_json_valid:   issues["planner_bad_json"].append(r.idx)
        if r.planner_fallback:         issues["planner_fallback"].append(r.idx)
        if r.planner_num_tasks == 0:   issues["planner_no_tasks"].append(r.idx)
        if r.reasoner_fallback:        issues["reasoner_fallback"].append(r.idx)
        if r.reasoner_health not in ("green","yellow","red"):
                                       issues["reasoner_bad_health"].append(r.idx)
        if r.comm_length < 200:        issues["comm_too_short"].append(r.idx)
        if not r.comm_uses_project_name: issues["comm_no_proj_name"].append(r.idx)
        if not r.comm_has_numbers:     issues["comm_no_numbers"].append(r.idx)
        if not r.comm_no_placeholders: issues["comm_has_placeholders"].append(r.idx)
        if not r.comm_coherent:        issues["comm_not_coherent"].append(r.idx)
        if not r.comm_type_matches_request: issues["comm_wrong_type"].append(r.idx)

    latencies = [r.latency_ms for r in successful]
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    p95_lat = sorted(latencies)[int(len(latencies)*0.95)] if latencies else 0

    health_dist = Counter(r.reasoner_health for r in successful)
    method_dist = Counter(r.planner_methodology for r in successful)
    comm_type_dist = Counter(r.comm_type for r in successful)

    return dict(
        total=total, successful=len(successful), failed=len(failed),
        avg_score=avg_score, scores=scores,
        issues=dict(issues),
        avg_latency_ms=avg_lat, p95_latency_ms=p95_lat,
        health_dist=dict(health_dist),
        method_dist=dict(method_dist),
        comm_type_dist=dict(comm_type_dist),
        failed_errors=[r.error for r in failed],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Auto-Adjustments
# ─────────────────────────────────────────────────────────────────────────────

def apply_adjustments(analysis: dict, inference_path: str) -> list[str]:
    """
    Read inference.py, apply safe parameter tweaks based on analysis,
    write back. Returns list of changes made.
    """
    changes = []
    issues = analysis["issues"]

    with open(inference_path) as f:
        src = f.read()

    original_src = src

    # If communicator output is too short (<200 chars) in >20% of cases,
    # increase min_new_tokens and max_new_tokens
    short_pct = len(issues.get("comm_too_short", [])) / max(1, analysis["successful"])
    if short_pct > 0.20:
        # Increase min_new_tokens from 60 to 80 in _run_communicator_phi3
        src = re.sub(
            r"(min_new_tokens=)60(\s*,\s*# phi3)",
            r"\g<1>80\g<2>", src
        )
        if src != original_src:
            changes.append(f"Increased min_new_tokens to 80 (comm too short in {short_pct:.0%} of cases)")

    # If planner fallback rate > 20%, tighten planner temperature to 0.15
    planner_fallback_pct = len(issues.get("planner_fallback", [])) / max(1, analysis["successful"])
    if planner_fallback_pct > 0.20:
        src = re.sub(
            r"(# Stage 1.*?temperature=)0\.2",
            r"\g<1>0.15",
            src, flags=re.DOTALL, count=1
        )
        if src != original_src:
            changes.append(f"Reduced planner temperature to 0.15 (fallback rate {planner_fallback_pct:.0%})")

    # If reasoner fallback rate > 20%, tighten reasoner temperature to 0.15
    reasoner_fallback_pct = len(issues.get("reasoner_fallback", [])) / max(1, analysis["successful"])
    if reasoner_fallback_pct > 0.20:
        src = re.sub(
            r"(# Stage 2.*?temperature=)0\.2",
            r"\g<1>0.15",
            src, flags=re.DOTALL, count=1
        )
        if src != original_src:
            changes.append(f"Reduced reasoner temperature to 0.15 (fallback rate {reasoner_fallback_pct:.0%})")

    if src != original_src:
        with open(inference_path, "w") as f:
            f.write(src)
        log(f"Applied {len(changes)} inference.py adjustments")
    else:
        log("No inference.py adjustments needed")

    return changes


# ─────────────────────────────────────────────────────────────────────────────
# Report Generation
# ─────────────────────────────────────────────────────────────────────────────

def write_report(
    round1_results: list[TestResult],
    round1_analysis: dict,
    round2_results: list[TestResult],
    round2_analysis: dict,
    adjustments: list[str],
    elapsed_minutes: float,
) -> None:

    def pct(n, d):
        return f"{n/max(1,d)*100:.1f}%"

    lines = [
        "# PMCore v6 — Overnight Evaluation Report",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Elapsed: {elapsed_minutes:.0f} minutes",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| | Round 1 (baseline) | Round 2 (post-adjustment) |",
        "|---|---|---|",
        f"| Tests run | {round1_analysis['total']} | {round2_analysis['total']} |",
        f"| Successful | {round1_analysis['successful']} ({pct(round1_analysis['successful'], round1_analysis['total'])}) | {round2_analysis['successful']} ({pct(round2_analysis['successful'], round2_analysis['total'])}) |",
        f"| Failed (API error) | {round1_analysis['failed']} | {round2_analysis['failed']} |",
        f"| Avg score (0–10) | {round1_analysis['avg_score']:.2f} | {round2_analysis['avg_score']:.2f} |",
        f"| Avg latency | {round1_analysis['avg_latency_ms']/1000:.1f}s | {round2_analysis['avg_latency_ms']/1000:.1f}s |",
        f"| p95 latency | {round1_analysis['p95_latency_ms']/1000:.1f}s | {round2_analysis['p95_latency_ms']/1000:.1f}s |",
        "",
        "---",
        "",
        "## Adjustments Made",
        "",
    ]

    if adjustments:
        for a in adjustments:
            lines.append(f"- {a}")
    else:
        lines.append("- No adjustments needed — all metrics within acceptable thresholds")

    lines += [
        "",
        "---",
        "",
        "## Issue Breakdown (Round 1 → Round 2)",
        "",
        "| Issue | Round 1 | Round 2 |",
        "|---|---|---|",
    ]

    all_issue_keys = sorted(set(round1_analysis["issues"]) | set(round2_analysis["issues"]))
    for key in all_issue_keys:
        n1 = len(round1_analysis["issues"].get(key, []))
        n2 = len(round2_analysis["issues"].get(key, []))
        lines.append(f"| `{key}` | {n1} ({pct(n1, round1_analysis['successful'])}) | {n2} ({pct(n2, round2_analysis['successful'])}) |")

    lines += [
        "",
        "---",
        "",
        "## Model Performance",
        "",
        "### PMPlanner",
        "",
        "**Methodology distribution (Round 2):**",
        "",
    ]
    for meth, cnt in sorted(round2_analysis["method_dist"].items(), key=lambda x: -x[1]):
        lines.append(f"- {meth or '(empty)'}: {cnt} ({pct(cnt, round2_analysis['successful'])})")

    lines += [
        "",
        "### PMReasoner",
        "",
        "**Health distribution (Round 2):**",
        "",
    ]
    for health, cnt in sorted(round2_analysis["health_dist"].items(), key=lambda x: -x[1]):
        lines.append(f"- {health or '(empty)'}: {cnt} ({pct(cnt, round2_analysis['successful'])})")

    lines += [
        "",
        "### PMCommunicator (Phi-3.5)",
        "",
        "**Communication type distribution (Round 2):**",
        "",
    ]
    for ct, cnt in sorted(round2_analysis["comm_type_dist"].items(), key=lambda x: -x[1]):
        lines.append(f"- {ct or '(empty)'}: {cnt} ({pct(cnt, round2_analysis['successful'])})")

    # Score distribution
    scores = round2_analysis["scores"]
    if scores:
        buckets = Counter(int(s) for s in scores)
        lines += ["", "**Score distribution (Round 2, 0–10):**", ""]
        for i in range(11):
            bar = "█" * buckets.get(i, 0)
            lines.append(f"  {i:2d} | {bar} {buckets.get(i,0)}")

    # Sample outputs — best and worst
    r2_sorted = sorted(round2_results, key=lambda r: r.score, reverse=True)
    good = [r for r in r2_sorted if r.success and r.score >= 8][:3]
    poor = [r for r in reversed(r2_sorted) if r.success and r.score < 6][:3]

    lines += ["", "---", "", "## Sample Outputs", "", "### Top Scoring Projects", ""]
    for r in good:
        lines += [
            f"**Test {r.idx} — Score {r.score:.0f}/10**",
            f"> {r.project[:100]}",
            f"```",
            r.comm_text,
            "```",
            "",
        ]

    lines += ["### Lowest Scoring Projects", ""]
    for r in poor:
        lines += [
            f"**Test {r.idx} — Score {r.score:.0f}/10** — {r.error or 'see issues'}",
            f"> {r.project[:100]}",
        ]
        if r.comm_text:
            lines += [f"```", r.comm_text[:300], "```"]
        lines.append("")

    if round2_analysis["failed_errors"]:
        lines += ["---", "", "## API Errors", ""]
        for e in round2_analysis["failed_errors"][:5]:
            lines.append(f"- {e}")

    lines += [
        "",
        "---",
        "",
        "## Recommendations",
        "",
    ]

    r2 = round2_analysis
    recs = []

    wrong_type_pct = len(r2["issues"].get("comm_wrong_type", [])) / max(1, r2["successful"])
    if wrong_type_pct > 0.30:
        recs.append(f"**Communication type matching is {wrong_type_pct:.0%}** — consider adding explicit comm_type routing in `_run_communicator` before passing to Phi-3.5 (e.g. prepend the type to the system prompt).")

    no_name_pct = len(r2["issues"].get("comm_no_proj_name", [])) / max(1, r2["successful"])
    if no_name_pct > 0.30:
        recs.append(f"**Project name not appearing in {no_name_pct:.0%} of outputs** — the `derive_project_name()` extraction may be too conservative. Consider including the first 100 chars of the raw request in the context JSON as `raw_request`.")

    fallback_pct = len(r2["issues"].get("planner_fallback", [])) / max(1, r2["successful"])
    if fallback_pct > 0.15:
        recs.append(f"**Planner fallback rate {fallback_pct:.0%}** — may benefit from a small targeted retrain on harder/longer project descriptions. Alternatively, reduce JSON prefix length to reduce token budget pressure.")

    avg_score = r2["avg_score"]
    if avg_score >= 8.0:
        recs.append(f"**Overall quality is high (avg {avg_score:.1f}/10)** — model is production-ready. Recommend proceeding with GitHub/HuggingFace publication.")
    elif avg_score >= 6.5:
        recs.append(f"**Overall quality is good (avg {avg_score:.1f}/10)** — recommend targeted improvements to weak dimensions before publication.")
    else:
        recs.append(f"**Overall quality needs improvement (avg {avg_score:.1f}/10)** — review top failure modes above before publication.")

    if not recs:
        recs.append("No significant issues detected. Ready for GitHub publication.")

    for rec in recs:
        lines.append(f"- {rec}")

    lines += ["", "---", f"*Report generated by overnight_eval.py — PMCore v6*"]

    report = "\n".join(lines)
    REPORT_PATH.write_text(report)
    log(f"Report written to {REPORT_PATH}")
    print("\n" + report)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_start = time.time()

    log("=" * 60)
    log("PMCore Overnight Evaluation — 200 full-pipeline tests")
    log("=" * 60)

    # Wait for API to be ready
    for attempt in range(10):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=10) as r:
                h = json.loads(r.read())
            if h.get("status") == "healthy":
                log(f"API healthy — VRAM: {h.get('gpu', {}).get('vram_used', '?')}")
                break
        except Exception:
            log(f"Waiting for API... attempt {attempt+1}/10")
            time.sleep(10)

    # ── Round 1: Baseline 200-test run ────────────────────────────────────────
    log("")
    log("ROUND 1: Running 200 baseline tests...")
    log("-" * 40)

    round1_results = []
    for i, (project, comm_req) in enumerate(PROJECTS, 1):
        r = run_test(i, project, comm_req)
        status = f"PASS ({r.score:.0f}/10)" if r.success else f"FAIL — {r.error}"
        comm_preview = r.comm_text[:60].replace('\n', ' ') if r.comm_text else ""
        log(f"  [{i:03d}/200] {status} | {r.latency_ms/1000:.1f}s | {comm_preview}")
        round1_results.append(r)

        # Brief progress summary every 25 tests
        if i % 25 == 0:
            so_far = [x for x in round1_results if x.success]
            avg = sum(x.score for x in so_far) / max(1, len(so_far))
            elapsed = (time.time() - t_start) / 60
            eta = elapsed / i * (200 - i)
            log(f"  --- Progress {i}/200 | Avg score: {avg:.2f}/10 | Elapsed: {elapsed:.0f}m | ETA: {eta:.0f}m ---")

    round1_analysis = analyze_results(round1_results)
    log("")
    log(f"Round 1 complete: {round1_analysis['successful']}/200 successful, avg score {round1_analysis['avg_score']:.2f}/10")

    # ── Adjustments ───────────────────────────────────────────────────────────
    log("")
    log("Analyzing results and applying adjustments...")
    inference_path = "pmcore/inference.py"
    adjustments = apply_adjustments(round1_analysis, inference_path)

    if adjustments:
        log("Adjustments applied — reloading API...")
        os.system("pkill -f 'uvicorn api:app' 2>/dev/null; sleep 5")
        os.system("nohup /home/snavazio/.local/bin/uv run python -m uvicorn api:app "
                  "--host 0.0.0.0 --port 8765 > api.log 2>&1 &")
        time.sleep(30)
        log("API restarted")
    else:
        log("No adjustments needed — skipping API restart")

    # ── Round 2: 200 tests post-adjustment ───────────────────────────────────
    log("")
    log("ROUND 2: Re-running all 200 tests post-adjustment...")
    log("-" * 40)

    random.shuffle(PROJECTS)  # different order
    round2_results = []
    for i, (project, comm_req) in enumerate(PROJECTS, 1):
        r = run_test(i, project, comm_req)
        status = f"PASS ({r.score:.0f}/10)" if r.success else f"FAIL — {r.error}"
        comm_preview = r.comm_text[:60].replace('\n', ' ') if r.comm_text else ""
        log(f"  [{i:03d}/200] {status} | {r.latency_ms/1000:.1f}s | {comm_preview}")
        round2_results.append(r)

        if i % 25 == 0:
            so_far = [x for x in round2_results if x.success]
            avg = sum(x.score for x in so_far) / max(1, len(so_far))
            log(f"  --- Progress {i}/200 | Avg score: {avg:.2f}/10 ---")

    round2_analysis = analyze_results(round2_results)
    log("")
    log(f"Round 2 complete: {round2_analysis['successful']}/200 successful, avg score {round2_analysis['avg_score']:.2f}/10")

    # ── Report ────────────────────────────────────────────────────────────────
    elapsed_minutes = (time.time() - t_start) / 60
    log("")
    log("Writing final report...")
    write_report(
        round1_results, round1_analysis,
        round2_results, round2_analysis,
        adjustments, elapsed_minutes,
    )

    log("")
    log("=" * 60)
    log("OVERNIGHT EVALUATION COMPLETE")
    log(f"  Round 1 avg score: {round1_analysis['avg_score']:.2f}/10")
    log(f"  Round 2 avg score: {round2_analysis['avg_score']:.2f}/10")
    log(f"  Adjustments made: {len(adjustments)}")
    log(f"  Elapsed: {elapsed_minutes:.0f} minutes")
    log(f"  Report: {REPORT_PATH}")
    log("=" * 60)


if __name__ == "__main__":
    main()
