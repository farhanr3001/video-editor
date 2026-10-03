param([string]$OutputWav)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SetOutputToWaveFile($OutputWav)
    $speaker.Speak('This is a test. What the fuck happened? Oh shit. Everything is fine now.')
} finally {
    $speaker.Dispose()
}
if ((Get-Item -LiteralPath $OutputWav).Length -lt 100) { throw 'Speech synthesis returned an empty audio fixture.' }
