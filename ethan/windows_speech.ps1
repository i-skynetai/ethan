param([ValidateSet('capabilities','capture','wake')][string]$Mode = 'capabilities')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Emit($value) { [Console]::Out.WriteLine(($value | ConvertTo-Json -Compress)); [Console]::Out.Flush() }
$recognizer = $null
try {
    Add-Type -AssemblyName System.Speech
    $engines = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
    if ($Mode -eq 'capabilities') {
        Emit @{ supported = ($engines.Count -gt 0); detail = "Installed local recognizers: $($engines.Count)" }
        exit 0
    }
    if ($engines.Count -eq 0) { throw 'No installed Windows local recognizer' }
    $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($engines[0])
    $recognizer.SetInputToDefaultAudioDevice()
    if ($Mode -eq 'wake') {
        $choices = New-Object System.Speech.Recognition.Choices
        $choices.Add('hey ethan')
        $builder = New-Object System.Speech.Recognition.GrammarBuilder
        $builder.Culture = $engines[0].Culture
        $builder.Append($choices)
        $recognizer.LoadGrammar((New-Object System.Speech.Recognition.Grammar($builder)))
        Emit @{ state='wake-listening'; detail='Local microphone on: say hey Ethan; expires in 60 seconds; cancel or mute to stop' }
        $wakeDeadline = [DateTime]::UtcNow.AddSeconds(60)
        $woke = $false
        while ([DateTime]::UtcNow -lt $wakeDeadline) {
            $heard = $recognizer.Recognize([TimeSpan]::FromSeconds(1))
            if ($heard -and $heard.Confidence -ge 0.75 -and $heard.Text -ieq 'hey ethan') { $woke = $true; break }
        }
        if (-not $woke) {
            Emit @{ state='idle'; transcript=''; detail='Wake listening expired; microphone off' }
            exit 0
        }
        $recognizer.UnloadAllGrammars()
    }
    $recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    Register-ObjectEvent -InputObject $recognizer -EventName SpeechRecognized -SourceIdentifier EthanSpeech | Out-Null
    Register-ObjectEvent -InputObject $recognizer -EventName RecognizeCompleted -SourceIdentifier EthanComplete | Out-Null
    $recognizer.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
    Emit @{ state='listening'; detail='Local microphone on; stop to preview, cancel to discard' }
    $stop = [Console]::In.ReadLineAsync()
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $stopping = $false
    $text = New-Object System.Collections.Generic.List[string]
    while ($true) {
        foreach ($e in @(Get-Event -SourceIdentifier EthanSpeech -ErrorAction SilentlyContinue)) {
            if ($e.SourceEventArgs.Result.Text) { $text.Add($e.SourceEventArgs.Result.Text) }
            Remove-Event -EventIdentifier $e.EventIdentifier
        }
        if (-not $stopping -and ($stop.IsCompleted -or [DateTime]::UtcNow -ge $deadline)) {
            $recognizer.RecognizeAsyncStop()
            $stopping = $true
            $deadline = [DateTime]::UtcNow.AddSeconds(3)
            Emit @{ state='transcribing'; detail='Finishing local transcript' }
        }
        if ($stopping -and ((Get-Event -SourceIdentifier EthanComplete -ErrorAction SilentlyContinue) -or [DateTime]::UtcNow -ge $deadline)) { break }
        Start-Sleep -Milliseconds 50
    }
    foreach ($e in @(Get-Event -SourceIdentifier EthanSpeech -ErrorAction SilentlyContinue)) {
        if ($e.SourceEventArgs.Result.Text) { $text.Add($e.SourceEventArgs.Result.Text) }
        Remove-Event -EventIdentifier $e.EventIdentifier
    }
    Emit @{ state='idle'; transcript=($text -join ' '); detail='Microphone off; preview only' }
} catch {
    Emit @{ state='error'; supported=$false; detail=$_.Exception.Message }
    exit 1
} finally {
    if ($recognizer) {
        try { $recognizer.RecognizeAsyncCancel() } catch { }
        finally { $recognizer.Dispose() }
    }
    Unregister-Event -SourceIdentifier EthanSpeech -ErrorAction SilentlyContinue
    Unregister-Event -SourceIdentifier EthanComplete -ErrorAction SilentlyContinue
    Get-Event -SourceIdentifier EthanSpeech -ErrorAction SilentlyContinue | Remove-Event
    Get-Event -SourceIdentifier EthanComplete -ErrorAction SilentlyContinue | Remove-Event
}
