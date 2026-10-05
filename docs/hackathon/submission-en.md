# InspirationSpace — Turn passing thoughts into considered views.

## Tagline

A bilingual desktop workspace where AI helps you examine ideas and you decide which views to accept.

## Problem

Saving an article, taking a note, or receiving an AI-generated answer can feel like progress. Yet none of those actions necessarily tells us what we believe, why we believe it, or what might change our minds.

Personal knowledge grows through judgment: turning an observation into a claim, testing its reasoning, considering objections, and deciding whether to accept it. Those steps are easy to lose in a folder of notes or a long chat history. As AI makes fluent answers readily available, we need tools that keep our own reasoning visible and our decisions deliberate.

## Solution

InspirationSpace is an open-source Windows desktop app organized around views: claims a person can examine and choose to accept. Its central workflow is **capture → distill → polish → confirm → revisit**.

Capture an inspiration in your own words. If it is an observation, question, or fragment, AI helps you explore it through conversation until you can articulate a claim. If it already expresses a claim, you can confirm a shortcut into polishing. In both cases, you control the transition.

In **Whetstone**, the polishing workspace, AI supplies a reason to adopt the view, its strongest counterargument, and suggestions for classification and relationships to existing views. You can challenge that analysis, discuss exceptions, and refine the text.

After you review and confirm the final wording and metadata, the view appears in **Anthology**, your collection of accepted views. The original inspiration remains available for tracing how the view developed. Accepted views can also be withdrawn for further discussion.

The central design choice is to separate AI assistance from user authority. AI generates analysis, questions, translations, and titles. The user decides what becomes an accepted view.

## Key Features

- **Two stages of thinking.** Distillation helps turn raw material into a claim; polishing tests that claim through reasons, objections, and discussion. A user-confirmed shortcut supports inspirations that already contain a clear claim.
- **A counterargument alongside the case for adoption.** The analysis schema requires both, making disagreement part of the workflow.
- **An editable adoption step.** Review the final text, Chinese and English titles, classification, tags, and proposed relationships before confirming acceptance.
- **Native Chinese and English support.** The interface supports both languages, with AI-assisted translations and bilingual titles for content. Content translation requires a configured AI provider.
- **An organized, revisitable collection.** Anthology offers table, card, and classified views, filters, and links between similar or conflicting views. A conflict records a relationship; it does not decide which view is correct.
- **A traceable thinking process.** Follow a view back to its source inspiration and retained analysis and discussion. AI call records and adoption decisions support inspection; explicit undo, reset, withdrawal, and deletion actions can remove the affected records.
- **A focused desktop interface.** A shared Hallmark design system uses a paper-like background, indigo text, blue actions, and gold accents. The three-column workbench keeps the queue, reasoning, and related views together, with independent scrolling.
- **Document workflows and configurable AI.** Import Word documents with a reviewable preview, export views to Word, and configure an OpenAI-compatible AI provider.

## Tech

The application combines **Python, FastAPI, SQLAlchemy, and SQLite** with a **React, Vite, and Tailwind CSS** frontend. **pywebview with Windows WebView2** supplies the desktop shell; **PyInstaller and Inno Setup** support Windows distribution.

The AI integration uses an OpenAI-compatible provider interface. Structured outputs are parsed and validated against **Pydantic schemas**. Business validation checks analysis suggestions, including permitted classifications and tags and references to existing views. Invalid outputs are surfaced as failures rather than treated as valid analysis.

AI-generated suggestions are separate from the adoption endpoint. On user confirmation, the backend commits the accepted text, metadata, selected relationships, decision record, and session completion in a **single database transaction**, rolling back the operation if it fails. AI calls record the provider, model, prompt version, input snapshot, and output or failure summary.

The local SQLite database stores the application's records. When AI features are used, relevant context is sent to the provider the user configures. The app can use a local OpenAI-compatible service; its AI features require a reachable model service.

Repository: [github.com/Bob-Heng/inspiration-space](https://github.com/Bob-Heng/inspiration-space)

## Target Users

InspirationSpace is designed for students working through readings, self-directed learners examining their assumptions, and readers or writers developing arguments across Chinese and English. It suits people who want to retain the reasoning behind a view and return to it as their understanding changes.

## Social Impact Statement

AI can help people express and examine ideas, but fluent output can also make a conclusion feel settled before the user has evaluated it. InspirationSpace makes the user's judgment an explicit step: consider an objection, revise a claim, and confirm what to accept. Its intended contribution is a practical habit of critical thinking and accountable use of AI. This is a design goal, not a claim of measured learning outcomes or demonstrated adoption.
