#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Webcamoid, webcam capture application.
# Copyright (C) 2017  Gonzalo Exequiel Pedone
#
# Webcamoid is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Webcamoid is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Webcamoid. If not, see <http://www.gnu.org/licenses/>.
#
# Web-Site: http://webcamoid.github.io/

import math
import os
import subprocess # nosec
import sys
import threading
import zipfile

import deploy_base
import tools.binary_pecoff
import tools.qt5


class Deploy(deploy_base.DeployBase, tools.qt5.DeployToolsQt):
    def __init__(self):
        super().__init__()
        self.targetSystem = 'posix_windows'
        self.installDir = os.path.join(self.buildDir, 'ports/deploy/temp_priv')
        self.pkgsDir = os.path.join(self.buildDir, 'ports/deploy/packages_auto/windows')
        self.detectQt(os.path.join(self.buildDir, 'StandAlone'))
        self.programName = 'webcamoid'
        self.rootInstallDir = os.path.join(self.installDir, self.programName)
        self.binaryInstallDir = os.path.join(self.rootInstallDir, 'bin')
        self.libInstallDir = self.qmakeQuery(var='QT_INSTALL_LIBS') \
                                .replace(self.qmakeQuery(var='QT_INSTALL_PREFIX'),
                                         self.rootInstallDir)
        self.libQtInstallDir = self.qmakeQuery(var='QT_INSTALL_ARCHDATA') \
                                .replace(self.qmakeQuery(var='QT_INSTALL_PREFIX'),
                                         self.rootInstallDir)
        self.qmlInstallDir = self.qmakeQuery(var='QT_INSTALL_QML') \
                                .replace(self.qmakeQuery(var='QT_INSTALL_PREFIX'),
                                         self.rootInstallDir)
        self.pluginsInstallDir = self.qmakeQuery(var='QT_INSTALL_PLUGINS') \
                                .replace(self.qmakeQuery(var='QT_INSTALL_PREFIX'),
                                         self.rootInstallDir)
        self.qtConf = os.path.join(self.binaryInstallDir, 'qt.conf')
        self.qmlRootDirs = ['StandAlone/share/qml', 'libAvKys/Plugins']
        self.mainBinary = os.path.join(self.binaryInstallDir, self.programName + '.exe')
        self.programName = os.path.splitext(os.path.basename(self.mainBinary))[0]
        self.programVersion = self.detectVersion(os.path.join(self.rootDir, 'commons.pri'))
        self.detectMake()
        self.binarySolver = tools.binary_pecoff.DeployToolsBinary()
        self.binarySolver.readExcludeList(os.path.join(self.rootDir, 'ports/deploy/exclude.{}.{}.txt'.format(os.name, sys.platform)))
        self.packageConfig = os.path.join(self.rootDir, 'ports/deploy/package_info.conf')
        self.dependencies = []
        self.installerConfig = os.path.join(self.installDir, 'installer/config')
        self.installerPackages = os.path.join(self.installDir, 'installer/packages')
        self.installerIconSize = 256
        self.appIcon = os.path.join(self.rootDir,
                                    'StandAlone/share/icons/hicolor/{1}x{1}/{0}.ico'.format(self.programName,
                                                                                            self.installerIconSize))
        self.licenseFile = os.path.join(self.rootDir, 'COPYING')
        self.installerRunProgram = '@TargetDir@/bin/' + self.programName + '.exe'
        self.installerScript = os.path.join(self.rootDir, 'ports/deploy/installscript.windows.qs')
        self.changeLog = os.path.join(self.rootDir, 'ChangeLog')
        self.targetArch = '64bit' if 'x86_64' in self.qtInstallBins else '32bit'

    @staticmethod
    def removeUnneededFiles(path):
        afiles = set()

        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith('.a') \
                    or f.endswith('.static.prl') \
                    or f.endswith('.pdb') \
                    or f.endswith('.lib'):
                    afiles.add(os.path.join(root, f))

        for afile in afiles:
            os.remove(afile)

    def prepare(self):
        print('Executing make install')
        self.makeInstall(self.buildDir, self.installDir)

        if self.targetArch == '32bit':
            self.binarySolver.sysBinsPath = ['/usr/i686-w64-mingw32/bin']
        else:
            self.binarySolver.sysBinsPath = ['/usr/x86_64-w64-mingw32/bin']

        self.binarySolver.detectStrip()

        if self.qtIFWVersion == '' or int(self.qtIFWVersion.split('.')[0]) < 3:
            appsDir = '@ApplicationsDir@'
        else:
            if self.targetArch == '32bit':
                appsDir = '@ApplicationsDirX86@'
            else:
                appsDir = '@ApplicationsDirX64@'

        self.installerTargetDir = appsDir + '/' + self.programName
        arch = 'win32' if self.targetArch == '32bit' else 'win64'
        self.outPackage = os.path.join(self.pkgsDir,
                                       '{}-{}-{}.exe'.format(self.programName,
                                                             self.programVersion,
                                                             arch))

        print('Copying Qml modules\n')
        self.solvedepsQml()
        print('\nCopying required plugins\n')
        self.solvedepsPlugins()
        print('\nRemoving Qt debug libraries')
        self.removeDebugs()
        print('Copying required libs\n')
        self.solvedepsLibs()
        print('\nWritting qt.conf file')
        self.writeQtConf()
        print('Stripping symbols')
        self.binarySolver.stripSymbols(self.installDir)
        print('Writting launcher file')
        self.createLauncher()
        print('Removing unnecessary files')
        self.removeUnneededFiles(self.installDir)
        print('\nWritting build system information\n')
        self.writeBuildInfo()

    def solvedepsLibs(self):
        deps = set(self.binarySolver.scanDependencies(self.installDir))
        extraDeps = ['libeay32.dll',
                     'ssleay32.dll',
                     'libEGL.dll',
                     'libGLESv2.dll',
                     'D3DCompiler_43.dll',
                     'D3DCompiler_46.dll',
                     'D3DCompiler_47.dll']

        for dep in extraDeps:
            path = self.whereBin(dep)

            if path != '':
                deps.add(path)

                for depPath in self.binarySolver.allDependencies(path):
                    deps.add(depPath)

        deps = sorted(deps)

        for dep in deps:
            depPath = os.path.join(self.binaryInstallDir, os.path.basename(dep))
            print('    {} -> {}'.format(dep, depPath))
            self.copy(dep, depPath)
            self.dependencies.append(dep)

    def removeDebugs(self):
        dbgFiles = set()

        for root, _, files in os.walk(self.libQtInstallDir):
            for f in files:
                if f.endswith('.dll'):
                    fname, ext = os.path.splitext(f)
                    dbgFile = os.path.join(root, '{}d{}'.format(fname, ext))

                    if os.path.exists(dbgFile):
                        dbgFiles.add(dbgFile)

        for f in dbgFiles:
            os.remove(f)

    def searchPackageFor(self, path):
        os.environ['LC_ALL'] = 'C'
        pacman = self.whereBin('pacman')

        if len(pacman) > 0:
            process = subprocess.Popen([pacman, '-Qo', path], # nosec
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, _ = process.communicate()

            if process.returncode != 0:
                return ''

            info = stdout.decode(sys.getdefaultencoding()).split(' ')

            if len(info) < 2:
                return ''

            package, version = info[-2:]

            return ' '.join([package.strip(), version.strip()])

        dpkg = self.whereBin('dpkg')

        if len(dpkg) > 0:
            process = subprocess.Popen([dpkg, '-S', path], # nosec
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, _ = process.communicate()

            if process.returncode != 0:
                return ''

            package = stdout.split(b':')[0].decode(sys.getdefaultencoding()).strip()

            process = subprocess.Popen([dpkg, '-s', package], # nosec
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, _ = process.communicate()

            if process.returncode != 0:
                return ''

            for line in stdout.decode(sys.getdefaultencoding()).split('\n'):
                line = line.strip()

                if line.startswith('Version:'):
                    return ' '.join([package, line.split()[1].strip()])

            return ''

        rpm = self.whereBin('rpm')

        if len(rpm) > 0:
            process = subprocess.Popen([rpm, '-qf', path], # nosec
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, _ = process.communicate()

            if process.returncode != 0:
                return ''

            return stdout.decode(sys.getdefaultencoding()).strip()

        return ''

    def commitHash(self):
        try:
            process = subprocess.Popen(['git', 'rev-parse', 'HEAD'], # nosec
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        cwd=self.rootDir)
            stdout, _ = process.communicate()

            if process.returncode != 0:
                return ''

            return stdout.decode(sys.getdefaultencoding()).strip()
        except:
            return ''

    @staticmethod
    def sysInfo():
        info = ''

        for f in os.listdir('/etc'):
            if f.endswith('-release'):
                with open(os.path.join('/etc' , f)) as releaseFile:
                    info += releaseFile.read()

        return info

    def writeBuildInfo(self):
        shareDir = os.path.join(self.rootInstallDir, 'share')

        try:
            os.makedirs(self.pkgsDir)
        except:
            pass

        depsInfoFile = os.path.join(shareDir, 'build-info.txt')

        # Write repository info.

        commitHash = self.commitHash()

        if len(commitHash) < 1:
            commitHash = 'Unknown'

        with open(depsInfoFile, 'w') as f:
            print('    Commit hash: ' + commitHash + '\n')
            f.write('Commit hash: ' + commitHash + '\n\n')

        # Write host info.

        info = self.sysInfo()

        with open(depsInfoFile, 'a') as f:
            for line in info.split('\n'):
                if len(line) > 0:
                    print('    ' + line)
                    f.write(line + '\n')

            print()
            f.write('\n')

        # Write Wine version and emulated system info.

        process = subprocess.Popen(['wine', '--version'], # nosec
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, _ = process.communicate()
        wineVersion = stdout.decode(sys.getdefaultencoding()).strip()

        with open(depsInfoFile, 'a') as f:
            print('    Wine Version: {}'.format(wineVersion))
            f.write('Wine Version: {}\n'.format(wineVersion))

        process = subprocess.Popen(['wine', 'cmd', '/c', 'ver'], # nosec
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        stdout, _ = process.communicate()
        fakeWindowsVersion = stdout.decode(sys.getdefaultencoding()).strip()

        if len(fakeWindowsVersion) < 1:
            fakeWindowsVersion = 'Unknown'

        with open(depsInfoFile, 'a') as f:
            print('    Windows Version: {}'.format(fakeWindowsVersion))
            f.write('Windows Version: {}\n'.format(fakeWindowsVersion))
            print()
            f.write('\n')

        # Write binary dependencies info.

        packages = set()

        for dep in self.dependencies:
            packageInfo = self.searchPackageFor(dep)

            if len(packageInfo) > 0:
                packages.add(packageInfo)

        packages = sorted(packages)

        with open(depsInfoFile, 'a') as f:
            for packge in packages:
                print('    ' + packge)
                f.write(packge + '\n')

    def createLauncher(self):
        path = os.path.join(self.rootInstallDir, self.programName) + '.bat'
        libDir = os.path.relpath(self.libInstallDir, self.rootInstallDir)
        qmlDir = os.path.relpath(self.qmlInstallDir, self.rootInstallDir).replace('/', '\\')

        with open(path, 'w') as launcher:
            launcher.write('@echo off\n')
            launcher.write('\n')
            launcher.write('rem Default values: desktop | angle | software\n')
            launcher.write('rem set QT_OPENGL=angle\n')
            launcher.write('\n')
            launcher.write('rem Default values: d3d11 | d3d9 | warp\n')
            launcher.write('rem set QT_ANGLE_PLATFORM=d3d11\n')
            launcher.write('\n')
            launcher.write('rem Default values: software | d3d12 | openvg\n')
            launcher.write('rem set QT_QUICK_BACKEND=""\n')
            launcher.write('\n')
            launcher.write('start /b "" '
                           + '"%~dp0bin\\{}" '.format(self.programName)
                           + '-p "%~dp0{}\\avkys" '.format(libDir)
                           + '-q "%~dp0{}" '.format(qmlDir)
                           + '-c "%~dp0share\\config"\n')

    @staticmethod
    def hrSize(size):
        i = int(math.log(size) // math.log(1024))

        if i < 1:
            return '{} B'.format(size)

        units = ['KiB', 'MiB', 'GiB', 'TiB']
        sizeKiB = size / (1024 ** i)

        return '{:.2f} {}'.format(sizeKiB, units[i - 1])

    def printPackageInfo(self, path):
        if os.path.exists(path):
            print('   ',
                  os.path.basename(path),
                  self.hrSize(os.path.getsize(path)))
            print('    sha256sum:', Deploy.sha256sum(path))
        else:
            print('   ',
                  os.path.basename(path),
                  'FAILED')

    def createPortable(self, mutex):
        arch = 'win32' if self.targetArch == '32bit' else 'win64'
        packagePath = \
            os.path.join(self.pkgsDir,
                         '{}-portable-{}-{}.zip'.format(self.programName,
                                                        self.programVersion,
                                                        arch))

        if not os.path.exists(self.pkgsDir):
            os.makedirs(self.pkgsDir)

        with zipfile.ZipFile(packagePath, 'w', zipfile.ZIP_DEFLATED, False) as zipFile:
            for root, dirs, files in os.walk(self.rootInstallDir):
                for f in dirs + files:
                    filePath = os.path.join(root, f)
                    dstPath = os.path.join(self.programName,
                                           filePath.replace(self.rootInstallDir + os.sep, ''))
                    zipFile.write(filePath, dstPath)

        mutex.acquire()
        print('Created portable package:')
        self.printPackageInfo(packagePath)
        mutex.release()

    def createAppInstaller(self, mutex):
        packagePath = self.createInstaller()

        if not packagePath:
            return

        mutex.acquire()
        print('Created installable package:')
        self.printPackageInfo(self.outPackage)
        mutex.release()

    def package(self):
        mutex = threading.Lock()

        threads = [threading.Thread(target=self.createPortable, args=(mutex,))]

        if self.qtIFW != '':
            threads.append(threading.Thread(target=self.createAppInstaller, args=(mutex,)))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
