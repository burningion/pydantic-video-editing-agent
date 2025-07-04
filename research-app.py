#!/usr/bin/env python3
"""
Deep Research Query App - A Textual application for iterative query refinement
"""

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Horizontal, Vertical
from textual.widgets import Input, Button, Static, LoadingIndicator, TextArea, MarkdownViewer, Select
from textual.reactive import reactive
from textual.binding import Binding
from textual import events
import asyncio
from openai import OpenAI
import os
from typing import Optional
from datetime import datetime


class QueryRefinementWidget(Static):
    """Widget to display the current query and its refinements"""
    
    def __init__(self, label: str, content: str = "", **kwargs):
        super().__init__(**kwargs)
        self.label = label
        self._content = content
    
    @property
    def content(self):
        return self._content
    
    @content.setter
    def content(self, value: str):
        self._content = value
        self.update(self.render_content())
    
    def render_content(self):
        return f"[bold cyan]{self.label}:[/bold cyan]\n{self._content}"
    
    def compose(self) -> ComposeResult:
        yield Static(self.render_content())


class ResearchApp(App):
    """A Textual app for deep research queries with iterative refinement"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #app-title {
        text-align: center;
        text-style: bold;
        margin: 1;
    }
    
    #step-indicator {
        text-align: center;
        margin: 1;
        color: $text-muted;
    }
    
    #content-area {
        margin: 1;
        padding: 2;
        border: solid $primary;
        height: 85%;
    }
    
    /* Disable scrolling on content-area when showing research output */
    .no-scroll {
        overflow: hidden;
    }
    
    #navigation {
        dock: bottom;
        height: 4;
        align: center middle;
    }
    
    #navigation Button {
        margin: 0 1;
        width: 20;
    }
    
    #query-input {
        width: 100%;
        margin: 1 0;
    }
    
    #model-select {
        width: 100%;
        margin: 1 0;
        min-height: 3;
    }
    
    Select > SelectCurrent {
        padding: 0 2;
    }
    
    #clarification-input {
        width: 100%;
        height: 15;
        margin: 1 0;
    }
    
    #research-output {
        width: 100%;
        height: 100%;
        min-height: 20;
    }
    
    LoadingIndicator {
        margin: 2;
    }
    
    .step-content {
        padding: 1;
    }
    
    .query-text {
        margin: 1 0;
        padding: 1;
        background: $boost;
    }
    
    .question-item {
        margin: 1 0;
        padding: 1;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+r", "reset", "Reset Query"),
    ]
    
    def __init__(self):
        super().__init__()
        # Set a very long timeout (2 hours) for deep research
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=7200.0  # 2 hours timeout
        )
        self.current_query = ""
        self.refined_query = ""
        self.refined_content = ""
        self.clarifying_questions = []
        self.clarifications = ""
        self.step = 0  # 0: initial query, 1: refinement review + clarifications, 2: research
        self.max_steps = 2
        self.research_task: Optional[asyncio.Task] = None
        self.research_results = ""
        self.saved_filename = ""
        self.showing_markdown = False
        self.research_completed = False
        self.selected_model = "o3-deep-research-2025-06-26"  # Default to o3
        
    def compose(self) -> ComposeResult:
        """Create the app layout"""
        yield Vertical(
            Static("Deep Research Query Assistant", id="app-title"),
            Static("Step 1 of 3: Enter your research query", id="step-indicator"),
            ScrollableContainer(
                id="content-area"
            ),
            Horizontal(
                Button("← Back", id="back-button", variant="default", disabled=True),
                Button("Next →", id="next-button", variant="primary"),
                id="navigation"
            )
        )
    
    async def on_mount(self) -> None:
        """Initialize the first step when app mounts"""
        await self.show_step(0)
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events"""
        # Debug: log button press
        button = event.button
        print(f"Button pressed: {button.id}, label: {button.label}")
        
        if event.button.id == "next-button":
            await self.handle_next()
        elif event.button.id == "back-button":
            await self.handle_back()
        elif event.button.id == "view-markdown-button":
            await self.show_markdown_report()
        elif event.button.id == "markdown-back-button":
            await self.hide_markdown_report()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        if event.input.id == "query-input":
            await self.handle_next()
    
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes"""
        if event.select.id == "model-select":
            self.selected_model = event.value
    
    async def handle_next(self) -> None:
        """Handle the next button press"""
        if self.step == 0:  # Initial query step
            query_input = self.query_one("#query-input", Input)
            self.current_query = query_input.value.strip()
            
            # Get selected model
            model_select = self.query_one("#model-select", Select)
            self.selected_model = model_select.value
            
            if not self.current_query:
                return
            
            # Show loading and refine query
            content_area = self.query_one("#content-area", ScrollableContainer)
            content_area.remove_children()
            content_area.mount(
                Static(f"[dim]Processing query: {self.current_query}[/dim]"),
                LoadingIndicator()
            )
            
            await self.refine_query()
            
        elif self.step == 1:  # Refinement review + clarification step
            clarification_input = self.query_one("#clarification-input", TextArea)
            self.clarifications = clarification_input.text.strip()
            
            # Start research
            self.step = 2
            await self.show_step(2)
            await self.perform_research()
            
        elif self.step == 2:  # Research complete, start new
            # Reset the app for new research
            self.action_reset()
    
    async def handle_back(self) -> None:
        """Handle the back button press"""
        back_button = self.query_one("#back-button", Button)
        
        # If the button says "Exit" at any step, exit the app
        if back_button.label == "Exit":
            print("Exiting app...")  # Debug
            self.exit()
            return
        
        # Check if this is a cancel operation during research
        if self.step == 2 and hasattr(self, '_research_running') and self._research_running:
            self._research_running = False
            output_area = self.query_one("#research-output", TextArea)
            output_area.text += "\n\n❌ Research cancelled by user\n"
            
            # Reset back button
            back_button.label = "← Back"
            back_button.disabled = True
            back_button.variant = "default"
            return
            
        if self.step > 0:
            self.step -= 1
            await self.show_step(self.step)
    
    async def refine_query(self) -> None:
        """Refine the query using OpenAI"""
        suggested_rewriting_prompt = """
        You will be given a research task by a user. Your job is NOT to complete the task yet, but instead to ask clarifying questions that would help you or another researcher produce a more specific, efficient, and relevant answer.

        GUIDELINES:
        1. **Maximize Relevance**
        - Ask questions that are *directly necessary* to scope the research output.
        - Consider what information would change the structure, depth, or direction of the answer.

        2. **Surface Missing but Critical Dimensions**
        - Identify essential attributes that were not specified in the user’s request (e.g., preferences, time frame, budget, audience).
        - Ask about each one *explicitly*, even if it feels obvious or typical.

        3. **Do Not Invent Preferences**
        - If the user did not mention a preference, *do not assume it*. Ask about it clearly and neutrally.

        4. **Use the First Person**
        - Phrase your questions from the perspective of the assistant or researcher talking to the user (e.g., “Could you clarify...” or “Do you have a preference for...”)

        5. **Use a Bulleted List if Multiple Questions**
        - If there are multiple open questions, list them clearly in bullet format for readability.

        6. **Avoid Overasking**
        - Prioritize the 3–6 questions that would most reduce ambiguity or scope creep. You don’t need to ask *everything*, just the most pivotal unknowns.

        7. **Include Examples Where Helpful**
        - If asking about preferences (e.g., travel style, report format), briefly list examples to help the user answer.

        8. **Format for Conversational Use**
        - The output should sound helpful and conversational—not like a form. Aim for a natural tone while still being precise.
        """
        
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4.1-2025-04-14",
                messages=[
                    {"role": "system", "content": suggested_rewriting_prompt},
                    {"role": "user", "content": self.current_query}
                ],
                temperature=0.7
            )
            
           
            self.refined_query = response.choices[0].message.content
            
            # Move to refinement review step
            self.step = 1
            await self.show_step(1)
            
        except Exception as e:
            content_area = self.query_one("#content-area", ScrollableContainer)
            content_area.remove_children()
            content_area.mount(
                Static(f"[red]Error refining query: {str(e)}[/red]")
            )
    
    async def show_step(self, step: int) -> None:
        """Show the appropriate step content"""
        content_area = self.query_one("#content-area", ScrollableContainer)
        content_area.remove_children()
        
        # Remove no-scroll class from previous steps
        content_area.remove_class("no-scroll")
        
        step_indicator = self.query_one("#step-indicator", Static)
        back_button = self.query_one("#back-button", Button)
        next_button = self.query_one("#next-button", Button)
        
        if step == 0:  # Initial query
            step_indicator.update("Step 1 of 3: Enter your research query")
            back_button.label = "Exit"
            back_button.disabled = False
            back_button.variant = "error"
            next_button.label = "Next →"
            next_button.disabled = False
            
            # Define model options - Select widget expects (label, value) tuples
            model_options = [
                ("o3 Deep Research (More thorough, ~$10-30)", "o3-deep-research-2025-06-26"),
                ("o4 Mini Deep Research (Faster, ~$3)", "o4-mini-deep-research-2025-06-26")
            ]
            
            content_area.mount(
                Vertical(
                    Static("[bold]Enter your research query:[/bold]", classes="step-content"),
                    Static("Be as specific as possible about what you want to research.", classes="step-content"),
                    Input(placeholder="Enter your research query...", id="query-input", value=self.current_query),
                    Static("\n[bold]Select research model:[/bold]", classes="step-content"),
                    Select(
                        options=model_options,
                        value=self.selected_model,
                        id="model-select"
                    ),
                    classes="step-content"
                )
            )
            
        elif step == 1:  # Refinement review + clarifications
            step_indicator.update("Step 2 of 3: Review and clarify")
            back_button.disabled = False
            next_button.label = "Start Research →"
            next_button.disabled = False
            
            content_area.mount(
                ScrollableContainer(
                    Static("[bold]Original Query:[/bold]", classes="step-content"),
                    Static(self.current_query, classes="query-text"),
                    Static("\n[bold]Refined Query:[/bold]", classes="step-content"),
                    Static(self.refined_query, classes="query-text"),
                    Static("\n[bold]Clarifying Questions:[/bold]", classes="step-content"),
                    *[Static(q, classes="question-item") for q in self.clarifying_questions],
                    Static("\n[dim]Please answer the clarifying questions below (optional):[/dim]", classes="step-content"),
                    TextArea(id="clarification-input", text=self.clarifications),
                )
            )
            
        elif step == 2:  # Research
            step_indicator.update("Step 3 of 3: Research results")
            next_button.label = "New Research"
            next_button.disabled = False
            
            # Check if research is completed
            if self.research_completed:
                back_button.label = "Exit"
                back_button.disabled = False
                back_button.variant = "error"
            else:
                back_button.disabled = True
                # Add cancel button during research
                if hasattr(self, '_research_running') and self._research_running:
                    back_button.label = "Cancel"
                    back_button.disabled = False
                    back_button.variant = "error"
            
            # Disable scrolling on content_area since TextArea has its own scrollbar
            content_area.add_class("no-scroll")
            
            # Create a TextArea that fills the container directly
            research_output = TextArea(id="research-output", read_only=True, soft_wrap=True)
            research_output.styles.height = "100%"
            research_output.styles.width = "100%"
            content_area.mount(research_output)
    
    
    async def update_progress(self, output_area: TextArea, start_time: datetime) -> None:
        """Update progress periodically while research is running"""
        dots = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        dot_index = 0
        last_heartbeat = 0
        
        while hasattr(self, '_research_running') and self._research_running:
            elapsed = (datetime.now() - start_time).total_seconds()
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            
            # Add heartbeat message every 10 seconds
            current_10s = int(elapsed // 10)
            if current_10s > last_heartbeat:
                last_heartbeat = current_10s
                output_area.text += f"\n[{datetime.now().strftime('%H:%M:%S')}] Still working... ({minutes}m {seconds}s elapsed)"
                
                # Scroll to bottom
                output_area.cursor_location = (output_area.document.line_count - 1, 0)
                output_area.scroll_cursor_visible(animate=False)
            
            # Update the last line with animated progress
            lines = output_area.text.split('\n')
            # Remove previous progress line
            if lines and "Research in progress..." in lines[-1]:
                lines = lines[:-1]
            
            status_msg = f"{dots[dot_index]} Research in progress... ({minutes:02d}:{seconds:02d} elapsed)"
            output_area.text = '\n'.join(lines + [status_msg])
            
            # Scroll to bottom to show the progress
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible(animate=False)
            
            dot_index = (dot_index + 1) % len(dots)
            await asyncio.sleep(0.5)
    
    async def perform_research(self) -> None:
        """Perform the actual deep research"""
        # Use the selected model
        model_name = self.selected_model
        
        output_area = self.query_one("#research-output", TextArea)
        output_area.text = f"[{datetime.now().strftime('%H:%M:%S')}] Starting deep research with {model_name}...\n\n"
        
        try:
            # Build instructions for deep research
            instructions = f"""Research Query: {self.refined_query}

Original Query: {self.current_query}"""
            
            if self.clarifications:
                instructions += f"""\n\nClarifications provided:
{self.clarifications}

Please incorporate these clarifications into your research."""
            
            if self.clarifying_questions:
                instructions += f"""\n\nQuestions that were asked:
{chr(10).join(self.clarifying_questions)}"""
            
            output_area.text += f"Research Query: {self.refined_query}\n\n"
            if self.clarifications:
                output_area.text += f"Clarifications:\n{self.clarifications}\n\n"
            
            output_area.text += "⏳ Status: Initializing deep research...\n"
            output_area.text += "This typically takes 5-20 minutes depending on query complexity.\n\n"
            
            start_time = datetime.now()
            self._research_running = True
            
            # Start progress update task
            progress_task = asyncio.create_task(self.update_progress(output_area, start_time))
            
            try:
                # Perform deep research
                output_area.text += f"[{datetime.now().strftime('%H:%M:%S')}] Sending request to deep research model...\n"
                output_area.text += "The AI is now searching the web and analyzing sources...\n\n"
                
                deep_research_call = await asyncio.to_thread(
                    self.client.responses.create,
                    # model="o4-mini-deep-research-2025-06-26", # cheaper, ~$3
                    model=model_name,
                    input=[
                        {
                            "role": "developer",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": instructions,
                                }
                            ]
                        },
                    ],
                    reasoning={
                        "summary": "auto"
                    },
                    tools=[
                        {
                            "type": "web_search_preview"
                        },
                    ],
                    timeout=7200.0  # 2 hour timeout for the API call itself
                )
            finally:
                # Stop progress updates
                self._research_running = False
                await progress_task
            
            # Calculate elapsed time
            elapsed = (datetime.now() - start_time).total_seconds()
            
            output_area.text += f"\n✅ Research completed successfully in {elapsed:.1f} seconds!\n\n"
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible()
            
            # Access the final report from the response object
            self.research_results = deep_research_call.output[-1].content[0].text
            
            output_area.text += "=" * 70 + "\n"
            output_area.text += "RESEARCH RESULTS:\n"
            output_area.text += "=" * 70 + "\n\n"
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible()
            
            # Add research results in chunks to allow for scrolling
            output_area.text += self.research_results
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible()
            
            output_area.text += "\n\n" + "=" * 70 + "\n"
            output_area.text += f"[{datetime.now().strftime('%H:%M:%S')}] End of research report\n"
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible()
            
            # Save to markdown file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research_{timestamp}.md"
            
            markdown_content = f"""# Research Report

**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Model:** {model_name}
**Research Duration:** {elapsed:.1f} seconds

## Original Query
{self.current_query}

## Refined Query
{self.refined_query}

## Clarifications
{self.clarifications if self.clarifications else 'None provided'}

## Research Results

{self.research_results}
"""
            
            with open(filename, 'w') as f:
                f.write(markdown_content)
            
            self.saved_filename = filename
            output_area.text += f"\n📄 Report saved to: {filename}\n"
            output_area.text += f"✅ All tasks completed successfully!\n"
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible()
            
            # Show completion time warning if it took a long time
            if elapsed > 600:  # More than 10 minutes
                mins = elapsed / 60
                output_area.text += f"\n⏱️  This research took {mins:.1f} minutes - quite a thorough investigation!\n"
                output_area.cursor_location = (output_area.document.line_count - 1, 0)
                output_area.scroll_cursor_visible()
            
            # Mark research as completed
            self.research_completed = True
            
            # Update buttons for completed research
            next_button = self.query_one("#next-button", Button)
            next_button.label = "New Research"
            next_button.disabled = False  # Ensure it's enabled
            next_button.visible = True
            
            back_button = self.query_one("#back-button", Button)
            back_button.label = "Exit"
            back_button.disabled = False
            back_button.variant = "error"
            back_button.visible = True
            
            # Force refresh the button to ensure it's clickable
            back_button.refresh()
            next_button.refresh()
            
            # Ensure buttons are in front
            navigation = self.query_one("#navigation", Horizontal)
            navigation.refresh()
            
            # Add view markdown button if file was saved
            if self.saved_filename:
                content_area = self.query_one("#content-area", ScrollableContainer)
                # Check if button already exists
                try:
                    content_area.query_one("#view-markdown-button")
                except:
                    # Add button at the top of the content area
                    text_area = content_area.query_one("#research-output")
                    content_area.remove_children()
                    content_area.mount(
                        Vertical(
                            Button("📄 View Markdown Report", id="view-markdown-button", variant="success"),
                            text_area
                        )
                    )
            
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds() if 'start_time' in locals() else 0
            mins = elapsed / 60
            output_area.text += f"\n\n❌ Error after {mins:.1f} minutes ({elapsed:.0f} seconds):\n"
            output_area.text += f"{str(e)}\n\n"
            
            # Check if it's a timeout error
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                output_area.text += "⏱️  The request timed out. This can happen with very complex queries.\n"
                output_area.text += "Consider:\n"
                output_area.text += "• Breaking down your query into smaller, more specific parts\n"
                output_area.text += "• Trying again - sometimes the API is just slow\n"
            else:
                output_area.text += "Troubleshooting tips:\n"
                output_area.text += "• Ensure your OPENAI_API_KEY is set correctly\n"
                output_area.text += "• Check that you have access to the o3-deep-research-2025-06-26 model\n"
                output_area.text += "• Verify your internet connection for web search\n"
                output_area.text += "• Note: Deep research can take 15-30+ minutes for complex queries\n"
            
            output_area.cursor_location = (output_area.document.line_count - 1, 0)
            output_area.scroll_cursor_visible()
            
            # Mark as completed even on error
            self.research_completed = True
            
            # Enable exit button even on error
            back_button = self.query_one("#back-button", Button)
            back_button.label = "Exit"
            back_button.disabled = False
            back_button.variant = "error"
            back_button.visible = True
            back_button.refresh()
            
            # Also ensure navigation is refreshed
            navigation = self.query_one("#navigation", Horizontal)
            navigation.refresh()
    
    def action_reset(self) -> None:
        """Reset the app to initial state"""
        self.current_query = ""
        self.refined_query = ""
        self.refined_content = ""
        self.clarifying_questions = []
        self.clarifications = ""
        self.step = 0
        self.research_results = ""
        self.saved_filename = ""
        self.showing_markdown = False
        self.research_completed = False
        # Keep the selected model from previous session
        
        # Cancel any running research task
        if self.research_task and not self.research_task.done():
            self.research_task.cancel()
        
        # Show initial step
        asyncio.create_task(self.show_step(0))


    async def show_markdown_report(self) -> None:
        """Show the markdown report in a full-screen viewer"""
        if not self.saved_filename or not os.path.exists(self.saved_filename):
            return
        
        self.showing_markdown = True
        
        # Read the markdown content
        with open(self.saved_filename, 'r') as f:
            markdown_content = f.read()
        
        # Clear the content area and show markdown viewer
        content_area = self.query_one("#content-area", ScrollableContainer)
        content_area.remove_children()
        
        # Create markdown viewer with back button
        content_area.mount(
            Vertical(
                Button("← Back to Results", id="markdown-back-button", variant="default"),
                MarkdownViewer(markdown_content, show_table_of_contents=True),
            )
        )
        
        # Update navigation buttons
        next_button = self.query_one("#next-button", Button)
        next_button.visible = False
        
        back_button = self.query_one("#back-button", Button)
        back_button.visible = False
        
        # Update step indicator
        step_indicator = self.query_one("#step-indicator", Static)
        step_indicator.update("Viewing Markdown Report")
    
    async def hide_markdown_report(self) -> None:
        """Return to the research results view"""
        self.showing_markdown = False
        await self.show_step(2)
        
        # Restore buttons with proper state
        next_button = self.query_one("#next-button", Button)
        next_button.visible = True
        next_button.label = "New Research"
        next_button.disabled = False
        
        back_button = self.query_one("#back-button", Button)
        back_button.visible = True
        back_button.label = "Exit"
        back_button.disabled = False
        back_button.variant = "error"
        
        # Force refresh
        back_button.refresh()
        next_button.refresh()
        
        # Re-add the markdown button if needed
        if self.saved_filename:
            content_area = self.query_one("#content-area", ScrollableContainer)
            try:
                content_area.query_one("#view-markdown-button")
            except:
                text_area = content_area.query_one("#research-output")
                content_area.remove_children()
                content_area.mount(
                    Vertical(
                        Button("📄 View Markdown Report", id="view-markdown-button", variant="success"),
                        text_area
                    )
                )


if __name__ == "__main__":
    app = ResearchApp()
    app.run()