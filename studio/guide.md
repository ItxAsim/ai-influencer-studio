## Build your character first (about 1 hour, once)

You do this once per character. Use any chatbot (Claude, ChatGPT, Gemini) for the text and any image tool
for the pictures. Copy each prompt and fill in the **[brackets]**.

### 1. Character profile
> Create a character profile for an AI influencer in the **[niche]** niche, for **[audience]**. Give:
> a name; age and nationality; a believable backstory (their job, the turning point, why they post);
> a distinct look that is recognisable in a thumbnail (face, hair, 2–3 signature details, clothes,
> colour palette); 3–4 everyday places they film in; a unique selling point (what they do that others
> in the niche don't); voice and tone; a catchphrase; and hard limits (what they never claim or say).
> They are openly AI-generated.

You'll copy parts of the result into the **Character** tab.
Tip: make them ordinary and specific (a real job, a real place, one flaw). Ordinary reads as human.

### 2. Character sheet (reference images)
> Photoreal character reference sheet of **[the look from the profile]**. Three panels on a plain white
> seamless background: full body standing relaxed; side profile, head and shoulders; front close-up
> portrait. The same person and outfit in every panel. Soft natural light, real skin texture with pores
> and small imperfections, not airbrushed, no text.

Generate until the face is one you'd believe. From now on, that face is the character.

### 3. Locations
> Empty location photograph, no people: **[place, e.g. small farmhouse kitchen]**, **[light, e.g. warm
> late-afternoon sun]**, taken on a phone at eye level, vertical 9:16, lived-in and real, no text, no brands.

Make one for each place in the profile.

### 4. The start frame (the photo the studio animates)
In an image tool that accepts two reference images:
> Put the person from image 1 into the place in image 2. Waist-up, facing the camera, relaxed, as if
> about to talk to a friend. Phone-camera look, vertical 9:16. Lit by the room's own light. Eyes looking
> into the lens, mouth closed and relaxed.

**The most important rule: the face must be big.** It should fill at least a quarter of the frame width, so
frame waist-up or closer, never full body. The video model works at 480×832, and a small face comes out with
smeared eyes.

### 5. Voice description
One paragraph describing how they sound:
> **[Gender]**, **[age]**, **[accent]**. **[Pitch]**, **[texture]** (e.g. a faint lived-in rasp, not radio
> polish). **[Pace]** with natural pauses. **[Personality in the delivery]** (e.g. dry warmth, never salesy).
> **[Recording style]** (e.g. intimate close-mic podcast).

### 6. Make videos
Work through the tabs from left to right:
1. **Character:** fill it in, upload the start frame, save.
2. **Script:** get ideas, write the script, then **Use this script**.
3. **Voice:** design the voice once (pick a take, **Use this voice**).
4. **Video:** it uses the script you saved in step 2. Click **🎬 Make the full video from this script**: it
   speaks the script, makes the clips, syncs the mouth and adds the title, subtitles and sound, all in one go.
5. **Lip-sync & finish:** only if you want to redo a step yourself, e.g. drop a bad take and re-sync.

After the first video, **Autopilot** on the Script tab does the same straight from a new script.
**Export character pack** saves the voice, so the character sounds the same in every video.

### If the connection drops, or Kaggle restarts
- **Closing the tab or losing the connection doesn't stop anything.** Steps run on the Kaggle machine, not in
  your browser. Reopen the link and the page reconnects to the running step and restores your character,
  script and results.
- **If the app or notebook restarts** (but the Kaggle session is still on), run the notebook again: a
  **▶ Resume** button appears at the top. Finished takes, voice-overs and lip-syncs are reused, so it carries on
  from where it stopped.
- **When the Kaggle session ends,** Kaggle deletes its files. Before that happens, tick **Full backup** and click
  **Export character pack** on the Character tab, then download the zip. In a new session, import it in the same
  place, and your character, voice, takes and videos are all back.

### Rules worth keeping
- **Say it's AI.** TikTok, Instagram and YouTube all require realistic AI-generated content to be labelled,
  so use their AI-content toggle. Never present the character as a real person or copy a real person's face.
- **Stay inside your niche's limits.** For health and money especially: no diagnosis, no guarantees, no
  invented studies. The script writer is told this, but you check every script before it's spoken.
- **Licences.** Check each model's licence before earning money with it (see the README). Remotion is free for
  individuals and companies of up to 3 people; larger companies need a licence.
