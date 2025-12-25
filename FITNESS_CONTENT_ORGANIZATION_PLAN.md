# Fitness Content Repository Organization Plan

## Current Situation

### Problem Summary
- **Working:** YouTube scraping → audio download → text conversion → Pinecone indexing
- **Blocked:** Wix frontend stuck in read-only mode, preventing code updates
- **Issue:** Repositories split across multiple locations from troubleshooting Wix issues

### Repositories Involved
1. **forged-by-freedom** - Main fitness content repository (8,930 files)
   - YouTube transcript scraping scripts
   - Audio/text processing
   - Pinecone integration
   
2. **forged-by-freedom-st1** - Wix website project (attempt 1)
3. **forged-by-freedom-st2** - Wix website project (attempt 2)
4. **forged-by-freedom-st3** - Wix website project (attempt 3 + searchServer.js)

### System Architecture
```
YouTube API
    ↓
Download Audio Files
    ↓
Convert to Text
    ↓
Delete Audio (save space)
    ↓
Index & Store in Pinecone
    ↓
Wix Frontend (READ-ONLY - BLOCKED)
    ↓
OpenRouter API
    ↓
Query Pinecone Database
    ↓
Generate Response:
    1. Detailed answer with podcast quotes
    2. Technical/scientific explanation (medical books)
    3. Motivational message from Coach Bryan
```

### Key Integrations (All Working)
- ✅ OpenAI
- ✅ Render (hosting)
- ✅ GitHub
- ✅ Pinecone (vector database)
- ✅ OpenRouter (LLM routing)
- ❌ Wix (stuck in read-only mode)

## Organization Goals

### 1. Consolidate Repository Structure
**Action:** Merge split repositories into single organized structure

**Proposed Structure:**
```
forged-by-freedom/
├── backend/
│   ├── scrapers/          # YouTube scraping scripts
│   ├── processors/        # Audio-to-text conversion
│   ├── pinecone/          # Vector DB integration
│   └── api/               # Backend API (Render)
├── frontend/
│   ├── wix/               # Wix/Velo code (currently read-only)
│   └── components/        # Reusable components
├── data/
│   ├── transcripts/       # Text files organized by podcast
│   ├── indexes/           # Episode indexes
│   └── references/        # Medical books, technical docs
├── config/
│   ├── wix.config.json
│   ├── pinecone.config
│   └── api-keys.example
├── scripts/
│   ├── sync_to_pinecone.py
│   ├── update_indexes.py
│   └── deploy_to_wix.sh
└── docs/
    ├── SETUP.md
    ├── TROUBLESHOOTING.md
    └── ARCHITECTURE.md
```

### 2. Fix Wix/Velo Read-Only Mode

**Common Causes & Solutions:**

#### A. Authentication Issues
```bash
# Re-authenticate Wix CLI
npm install -g @wix/cli
wix login
wix site list
wix site select <your-site-id>
```

#### B. Developer Mode Not Enabled
- Go to Wix Dashboard → Settings → Developer Tools
- Enable "Velo Development Mode"
- Enable "Developer Tools" toggle

#### C. File Sync Issues
- Wix Editor: Dev Mode → Code Files
- Check if files are marked as "Editor Managed" (read-only)
- Switch to "Developer Managed" for custom code

#### D. Permissions/Ownership
- Verify you're site owner (not collaborator)
- Check Roles & Permissions in site settings
- May need to transfer ownership if site was created by different account

#### E. Git Sync Conflicts
```bash
# Check current Wix git status
cd forged-by-freedom-st3  # or whichever has latest
wix code pull
# Resolve any conflicts
wix code push
```

### 3. Migration Steps

#### Phase 1: Code Audit (Week 1)
- [ ] Clone all 4 repositories locally
- [ ] Identify duplicate code across repos
- [ ] Map dependencies and integrations
- [ ] Document current Wix site structure
- [ ] Export all Wix code/configurations

#### Phase 2: Consolidation (Week 1-2)
- [ ] Create new clean repository structure
- [ ] Migrate backend scripts to `/backend`
- [ ] Organize transcripts in `/data`
- [ ] Merge Wix code from st1/st2/st3
- [ ] Update all import paths
- [ ] Test integrations (Pinecone, OpenRouter, etc.)

#### Phase 3: Wix Troubleshooting (Week 2)
- [ ] Create fresh Wix site or fix existing
- [ ] Set up Wix CLI properly
- [ ] Enable developer mode
- [ ] Test code deployment
- [ ] Verify read-write access

#### Phase 4: Deployment (Week 3)
- [ ] Deploy backend to Render
- [ ] Deploy frontend to Wix
- [ ] Configure environment variables
- [ ] Test end-to-end flow
- [ ] Monitor for issues

#### Phase 5: Cleanup (Week 3-4)
- [ ] Archive old repositories (st1, st2, st3)
- [ ] Update documentation
- [ ] Create deployment runbook
- [ ] Set up monitoring/alerts

## Immediate Next Steps

### Step 1: Diagnose Wix Read-Only Issue
1. Check current Wix CLI authentication status
2. Verify site permissions in Wix dashboard
3. Confirm developer mode is enabled
4. Check if code files are editor-managed vs developer-managed

### Step 2: Repository Assessment
1. Clone all 4 repositories
2. Inventory all Python scripts
3. Map out current file organization
4. Identify critical vs duplicate files

### Step 3: Create Backup
1. Export all current code
2. Backup Pinecone indexes
3. Document current configurations
4. Save API credentials securely

## Wix Read-Only Troubleshooting Checklist

### Quick Fixes to Try First:
- [ ] Run `wix logout` then `wix login`
- [ ] Check Wix Dashboard → Dev Mode is ON
- [ ] Verify you're logged in as site owner
- [ ] Try creating new Wix site from scratch
- [ ] Check if files are in `.wix/` hidden folder
- [ ] Clear Wix CLI cache: `rm -rf ~/.wix`
- [ ] Reinstall Wix CLI: `npm uninstall -g @wix/cli && npm install -g @wix/cli`

### If Still Read-Only:
- [ ] Contact Wix Support with site ID
- [ ] Check for pending site transfers
- [ ] Verify payment/subscription status
- [ ] Try different computer/account
- [ ] Consider migrating to new Wix site

## Questions to Answer

1. **Which Wix site is the production site?**
2. **Do you have owner access to the Wix account?**
3. **What specific error message appears when trying to edit code?**
4. **Are you using Wix CLI or Wix Editor for code changes?**
5. **Has the site ever been editable, or always read-only?**
6. **Which repository (st1/st2/st3) has the most recent/working code?**

## Success Criteria

- [ ] Single consolidated repository
- [ ] Clear documentation of all components
- [ ] Wix site editable (not read-only)
- [ ] End-to-end search functionality working
- [ ] Automated deployment pipeline
- [ ] Monitoring and error handling
- [ ] Backup and recovery procedures

## Resources

### Wix Velo Documentation
- https://www.wix.com/velo/reference/
- https://dev.wix.com/docs/develop-websites/articles/getting-started

### Wix CLI
- https://dev.wix.com/docs/build-apps/developer-tools/cli/get-started

### Common Issues
- Read-only mode: https://support.wix.com/en/article/velo-troubleshooting-developer-mode

---

**Created:** 2025-12-25  
**Status:** Planning Phase  
**Next Action:** Diagnose Wix read-only issue and assess repository state
