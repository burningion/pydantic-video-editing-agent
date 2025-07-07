## Input

you are an award winning documentary producer. your job is to create a set of 6 visual beats to go with this narrative, each 5 seconds long, and adding up to a total of 30 seconds. you should return a json object with a description of the scene, and a set of search terms to look for footage from. here's the subsection: {{subsection}}

### Subsection

> Nathan Fielder’s journey began in the Canadian comedy scene, where he first honed the techniques that would define his style. After earning a business degree in 2005, Fielder pivoted to comedy and moved to Toronto to study improv and make short films (https://www.thecanadianencyclopedia.ca/en/article/nathan-fielder). Between 2006 and 2011, he created DIY comedy videos and shorts, some of which he uploaded to YouTube, showcasing his talent for uncomfortable humor in embryonic form (https://www.vulture.com/article/nathan-fielder-best-early-comedy-videos.html). His big break came with a segment on the CBC’s satirical news show *This Hour Has 22 Minutes* (2007–2009), where he developed a recurring bit called “Nathan On Your Side” (https://www.thecanadianencyclopedia.ca/en/article/nathan-fielder). In these segments, Fielder played a naïvely earnest consumer watchdog, ambushing real people and officials with bizarre questions in a flat, serious tone. This early work introduced viewers to Fielder’s awkward persona – soft-spoken, painfully sincere, and unflinchingly deadpan – which often made those around him squirm or puzzle over whether he was joking. Many hallmarks of his later comedy were already evident: a zealous commitment to the bit, interactions that teetered between sincere and absurd, and a fascination with how ordinary people respond to uncomfortable situations (https://www.vulture.com/article/nathan-fielder-best-early-comedy-videos.html). These Canadian projects essentially served as a proving ground for Fielder’s signature style, allowing him to refine the art of making audiences (and his unwitting subjects) question what was real and what was satire.

## Output 1 (~2 minutes)

```
{
"total_duration_seconds": 30,
"beats": [
{
"beat": 1,
"start_time": "00:00",
"end_time": "00:05",
"description": "Nighttime exterior of a modest Vancouver comedy club, neon sign flickering. Inside, a young Nathan Fielder steps up to a tiny stage with a microphone as a handful of patrons watch—setting the scene for his early Canadian stand-up roots.",
"search_terms": [
"small Canadian comedy club 2000s",
"open-mic stand-up Vancouver",
"neon comedy club exterior night",
"archival footage young comedian on stage"
]
},
{
"beat": 2,
"start_time": "00:05",
"end_time": "00:10",
"description": "Quick cross-cut montage: Fielder in cap and gown receiving a business diploma, then tossing textbooks into a cardboard box and rolling a suitcase toward a bustling Toronto skyline—his pivot from business graduate to aspiring comic.",
"search_terms": [
"2005 university graduation ceremony Canada",
"student packing belongings dorm room",
"rolling suitcase train station 2000s",
"early 2000s Toronto skyline timelapse"
]
},
{
"beat": 3,
"start_time": "00:10",
"end_time": "00:15",
"description": "Inside a cramped improv classroom: students form a circle, laughing mid-exercise. Smash cut to Fielder holding a handheld DV cam directing friends, then an over-the-shoulder shot of an old CRT monitor as a YouTube upload bar crawls across the screen.",
"search_terms": [
"improv class warm-up Toronto",
"aspiring filmmakers DV camera 2000s",
"early YouTube upload computer screen",
"handheld short film behind the scenes"
]
},
{
"beat": 4,
"start_time": "00:15",
"end_time": "00:20",
"description": "Bright CBC studio corridor transitions to Fielder on set of 'This Hour Has 22 Minutes.' He stands deadpan with microphone emblazoned with CBC logo, then ambushes a suited official outside a government building—introducing 'Nathan On Your Side.'",
"search_terms": [
"CBC newsroom hallway 2000s",
"This Hour Has 22 Minutes taping",
"Canadian satirical news show set",
"man with microphone interviewing official street"
]
},
{
"beat": 5,
"start_time": "00:20",
"end_time": "00:25",
"description": "Close-ups of puzzled faces: a cashier blinking, a passerby half-smiling, an official shifting uncomfortably. Cut between them and Fielder’s unflinching, soft-spoken stare—capturing the birth of his trademark awkward tension.",
"search_terms": [
"awkward interview reactions",
"people looking uncomfortable silence",
"deadpan comedian close-up",
"social discomfort candid street"
]
},
{
"beat": 6,
"start_time": "00:25",
"end_time": "00:30",
"description": "Dimly lit edit suite: Fielder leans in toward a glowing monitor, reviewing rough cuts of his segments. He cracks a subtle smile, silhouetted by the screen—signifying these Canadian experiments as the proving ground for his future style.",
"search_terms": [
"late-night video editing room",
"filmmaker alone reviewing footage",
"dark post-production studio 2000s",
"young comedian watching monitor"
]
}
]
}
```

## Output 2 (1m36s generation time, 442t up, 989t down)

```
{
"beats": [
{
"duration_seconds": 5,
"description": "Wide shot of a Canadian university graduation circa mid-2000s: students in black gowns file past a banner reading “Class of 2005.” One graduate clutches both a business diploma and a small notepad with scribbled joke ideas—hinting at Nathan Fielder’s pivot from business to comedy.",
"footage_search_terms": [
"2005 Canadian university graduation ceremony",
"business graduate holding diploma",
"student jotting comedy notes",
"mid 2000s campus footage"
]
},
{
"duration_seconds": 5,
"description": "Cut to bustling Toronto streets at dusk, then push inside a basement improv theatre. A young performer steps into a spotlight as classmates form a supportive semicircle—visualizing Fielder’s move to Toronto to study improv.",
"footage_search_terms": [
"Toronto skyline dusk 2000s",
"small improv class rehearsal",
"underground comedy club interior",
"young comedians on stage"
]
},
{
"duration_seconds": 5,
"description": "Handheld camcorder footage of a bedroom studio: tripod, cheap green screen, and an old CRT monitor displaying early-era YouTube. Quick cuts of quirky DIY comedy bits being filmed, capturing Fielder’s 2006-2011 YouTube shorts phase.",
"footage_search_terms": [
"early youtube video creation 2007",
"handheld camcorder diy comedy",
"bedroom green screen setup",
"retro computer monitor uploading video"
]
},
{
"duration_seconds": 5,
"description": "Studio graphic: CBC’s ‘This Hour Has 22 Minutes.’ Smash to Fielder-style street ambush—host with microphone labeled “Nathan On Your Side” confronting a suited official outside city hall.",
"footage_search_terms": [
"CBC news parody set",
"This Hour Has 22 Minutes archive",
"street interview microphone logo",
"reporter questioning politician Canada"
]
},
{
"duration_seconds": 5,
"description": "Montage of puzzled citizens: a cashier, an office manager, a passerby—each blinking, shifting, or half-smiling uncomfortably in response to off-camera questions, illustrating Fielder’s awkward interactions.",
"footage_search_terms": [
"awkward street reactions",
"people confused interview",
"uncomfortable customer service moment",
"deadpan prank response faces"
]
},
{
"duration_seconds": 5,
"description": "Close-up on Fielder’s expressionless face dissolves into a split-screen of real-world scenes and absurd on-screen graphics, ending with a quick rack-focus to a question mark—symbolizing the blurred line between satire and reality that his Canadian work refined.",
"footage_search_terms": [
"deadpan comedian close up",
"split screen reality vs satire",
"question mark graphic overlay",
"documentary montage ending"
]
}
]
}```