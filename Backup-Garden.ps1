$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework
[xml]$layout = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Title="Garden of Flies wallet backup" Height="390" Width="520" WindowStartupLocation="CenterScreen" ResizeMode="NoResize" Background="#F3F3E8">
 <StackPanel Margin="28">
  <TextBlock FontSize="24" Text="Protect your ten fly wallets" Margin="0,0,0,15"/>
  <TextBlock TextWrapping="Wrap" Text="Choose a password of at least 16 characters. It stays on this computer and is never sent to the website or chat." Margin="0,0,0,16"/>
  <TextBlock Text="Backup password"/><PasswordBox Name="First" Margin="0,6,0,12" Padding="7"/>
  <TextBlock Text="Repeat password"/><PasswordBox Name="Second" Margin="0,6,0,14" Padding="7"/>
  <Button Name="Save" Content="Create encrypted backup" Padding="10"/>
  <TextBlock Name="Result" TextWrapping="Wrap" Margin="0,14,0,0"/>
 </StackPanel>
</Window>
'@
$window = [Windows.Markup.XamlReader]::Load([System.Xml.XmlNodeReader]::new($layout))
$first = $window.FindName('First'); $second = $window.FindName('Second')
$save = $window.FindName('Save'); $result = $window.FindName('Result')
$save.Add_Click({
 if ($first.Password.Length -lt 16 -or $first.Password -cne $second.Password) { $result.Text='Use matching passwords of at least 16 characters.'; return }
 $save.IsEnabled=$false
 try {
  $info=[System.Diagnostics.ProcessStartInfo]::new()
  $info.FileName="$PSScriptRoot\.venv\Scripts\python.exe"
  $info.Arguments='"'+$PSScriptRoot+'\backup_wallets.py" --stdin-base64'
  $info.UseShellExecute=$false; $info.CreateNoWindow=$true
  $info.RedirectStandardInput=$true; $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
  $process=[System.Diagnostics.Process]::Start($info)
  $transport=[Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($first.Password))
  $process.StandardInput.WriteLine($transport); $process.StandardInput.Close(); $transport=$null
  $first.Clear(); $second.Clear()
  $output=$process.StandardOutput.ReadToEnd(); $failure=$process.StandardError.ReadToEnd(); $process.WaitForExit()
  if ($process.ExitCode -ne 0) { throw 'Backup failed; no funding is enabled.' }
  $result.Text='Backup verified. Save a separate copy of the encrypted file and retain its password.'
  $dialog=[Microsoft.Win32.SaveFileDialog]::new();$dialog.Title='Save a separate copy of your encrypted wallets';$dialog.Filter='Encrypted wallet backup (*.json)|*.json';$dialog.FileName='Garden-of-Flies-wallet-backup.json'
  if ($dialog.ShowDialog()) {
   $proof=Get-Content -LiteralPath "$PSScriptRoot\.garden\backup-proof.json" -Raw | ConvertFrom-Json
   Copy-Item -LiteralPath (Join-Path "$PSScriptRoot\.garden\backups" $proof.filename) -Destination $dialog.FileName
   $result.Text='Your encrypted backup is verified and copied. Keep its password safe.'
  }
 } catch { $result.Text='Backup could not finish. No funds have moved.'; $save.IsEnabled=$true }
})
$null=$window.ShowDialog()
