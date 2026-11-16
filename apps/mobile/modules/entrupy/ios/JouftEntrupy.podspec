Pod::Spec.new do |s|
  s.name = 'JouftEntrupy'
  s.version = '0.1.0'
  s.summary = 'Entrupy SDK bridge for Jouft'
  s.description = s.summary
  s.license = 'MIT'
  s.author = 'Jouft'
  s.homepage = 'https://jouft.com'
  s.platforms = { :ios => '15.8' }
  s.source = { :git => '' }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.dependency 'EntrupySDK', '2.3.6'
  s.source_files = '**/*.swift'
  s.swift_version = '5.9'
end
